import uuid

from django.conf import settings
from django.db import models

from .managers import ProjectManager, AppManager, EndpointManager, EnvironmentManager


# Retained only so historical migrations that referenced this upload_to
# callable still import. The app-icon image field itself has been removed.
def app_icon_path(instance, filename):
    return f"app_icons/{instance.id}.jpg"


class Project(models.Model):
    """
    Represents a top-level organizational unit for grouping related apps/services.
    Projects own API keys and provide aggregated analytics.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="projects",
    )
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=120, db_index=True)
    description = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ProjectManager()

    class Meta:
        db_table = "projects"
        ordering = ["-created_at"]
        constraints = [
            # Project slugs (and therefore names) are globally unique across all
            # users. Scoped to active rows so a soft-deleted project frees its
            # name for reuse.
            models.UniqueConstraint(
                fields=["slug"],
                condition=models.Q(is_active=True),
                name="unique_active_project_slug",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.slug})"


class App(models.Model):
    class Framework(models.TextChoices):
        FASTAPI = "fastapi"
        FLASK = "flask"
        DJANGO = "django"
        STARLETTE = "starlette"
        EXPRESS = "express"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.CASCADE,
        related_name="apps",
    )
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=120, db_index=True)
    icon = models.CharField(max_length=8, blank=True, default="")
    description = models.TextField(blank=True, default="")
    framework = models.CharField(
        max_length=24,
        choices=Framework.choices,
        default=Framework.FASTAPI,
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = AppManager()

    class Meta:
        db_table = "apps"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["project", "slug"],
                name="unique_app_slug_per_project",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.slug})"


class Endpoint(models.Model):
    """
    Represents a monitored API endpoint belonging to an App.
    """

    class Method(models.TextChoices):
        GET = "GET"
        POST = "POST"
        PUT = "PUT"
        PATCH = "PATCH"
        DELETE = "DELETE"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    app = models.ForeignKey(
        "projects.App",
        on_delete=models.CASCADE,
        related_name="endpoints",
    )
    path = models.CharField(max_length=500)
    method = models.CharField(max_length=10, choices=Method.choices, default=Method.GET)
    description = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = EndpointManager()

    class Meta:
        db_table = "endpoints"
        ordering = ["path", "method"]
        constraints = [
            models.UniqueConstraint(
                fields=["app", "path", "method"],
                name="unique_endpoint_per_app",
            ),
        ]

    def __str__(self):
        return f"{self.method} {self.path}"


class Environment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    app = models.ForeignKey(
        "projects.App",
        on_delete=models.CASCADE,
        related_name="environments",
    )
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=120)
    color = models.CharField(max_length=7, default="#6b7280")
    order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = EnvironmentManager()

    class Meta:
        db_table = "environments"
        ordering = ["order", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["app", "slug"],
                name="unique_environment_slug_per_app",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.app.name})"


class ProjectMember(models.Model):
    """A user's role-based membership in a project (RBAC subject).

    The project's `owner` is the authoritative owner and is NOT stored here;
    membership rows cover collaborators (admin / member / viewer). Effective role
    resolution prefers Project.owner, then this table.
    """

    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        ADMIN = "admin", "Admin"
        MEMBER = "member", "Member"
        VIEWER = "viewer", "Viewer"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="members"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="project_memberships",
    )
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.MEMBER)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "project_members"
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["project", "user"], name="unique_member_per_project"
            ),
        ]

    def __str__(self):
        return f"{self.user_id} @ {self.project_id} ({self.role})"


class AlertEvent(models.Model):
    """An anomaly detected on a project endpoint by the baseline-deviation job.

    Rows are written by the `detect_anomalies` job when an endpoint's error rate
    or p95 latency deviates from its own trailing hour-of-day-matched baseline.
    `dedup_key` (kind:method:path:YYYY-MM-DD) caps alerts at one per endpoint,
    metric, and day so a sustained incident doesn't flood the feed. Rows are
    harmless orphans if the feature is killed via APILENS_ANOMALY_ALERTS — the
    rollback story depends on that, so keep this table free of anything other
    code paths read.
    """

    class Kind(models.TextChoices):
        ERROR_RATE = "error_rate", "Error rate"
        LATENCY = "latency", "Latency"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        DISMISSED = "dismissed", "Dismissed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="alert_events"
    )
    app = models.ForeignKey(
        "projects.App",
        on_delete=models.CASCADE,
        related_name="alert_events",
        null=True,
        blank=True,
    )
    kind = models.CharField(max_length=20, choices=Kind.choices)
    method = models.CharField(max_length=10)
    path = models.CharField(max_length=500)
    observed_value = models.FloatField()
    baseline_value = models.FloatField()
    threshold_value = models.FloatField()
    window_start = models.DateTimeField()
    window_end = models.DateTimeField()
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ACTIVE, db_index=True
    )
    # First time any member clicked through to investigate. Never overwritten;
    # dismissed-with-viewed_at-null is the false-positive proxy the launch
    # guardrail (<40% dismissal-without-view) is computed from.
    viewed_at = models.DateTimeField(null=True, blank=True)
    dismissed_at = models.DateTimeField(null=True, blank=True)
    dismissed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    dedup_key = models.CharField(max_length=560)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "alert_events"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["project", "status", "-created_at"])]
        constraints = [
            models.UniqueConstraint(
                fields=["project", "dedup_key"], name="unique_alert_dedup_per_project"
            ),
        ]

    def __str__(self):
        return f"{self.kind} {self.method} {self.path} ({self.status})"


class JobHeartbeat(models.Model):
    """Last-completed-cycle record for background jobs (one row per job).

    Written at the end of every successful cycle so ops can distinguish "the
    job is running and found nothing" from "the job silently died" — the
    failure mode G3 review flagged for the anomaly detector. Exposed (name +
    freshness only, no project data) via the unauthenticated /health/jobs
    endpoint for external monitors.
    """

    name = models.CharField(max_length=100, primary_key=True)
    last_run_at = models.DateTimeField()
    last_scanned = models.IntegerField(default=0)
    last_created = models.IntegerField(default=0)
    last_duration_ms = models.IntegerField(default=0)

    class Meta:
        db_table = "job_heartbeats"

    def __str__(self):
        return f"{self.name} @ {self.last_run_at}"


class ProjectInvitation(models.Model):
    """A pending email invitation to join a project with a role.

    The invitee must explicitly accept (from the notification bell or the invite
    link); accepting creates the ProjectMember row. The magic-link flow
    auto-creates the account on first sign-in, but membership is never granted
    without an explicit accept. The invitee may also decline.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        REVOKED = "revoked", "Revoked"
        DECLINED = "declined", "Declined"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="invitations"
    )
    email = models.EmailField(db_index=True)
    role = models.CharField(
        max_length=20,
        choices=ProjectMember.Role.choices,
        default=ProjectMember.Role.MEMBER,
    )
    token_hash = models.CharField(max_length=64, unique=True, db_index=True)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "project_invitations"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["email", "status"])]

    @property
    def is_expired(self) -> bool:
        from django.utils import timezone

        return self.expires_at <= timezone.now()

    def __str__(self):
        return f"invite {self.email} -> {self.project_id} ({self.role}, {self.status})"
