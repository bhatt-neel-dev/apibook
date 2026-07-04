from django.test import TestCase

from apps.projects.membership import MembershipService
from apps.projects.models import Project, ProjectInvitation
from apps.users.models import User
from core.exceptions.base import ValidationError


class MembershipServiceTests(TestCase):
    def setUp(self) -> None:
        self.owner = User.objects.create(email="owner@example.com")
        self.project = Project.objects.create(
            owner=self.owner,
            name="Demo Project",
            slug="demo-project",
        )

    def test_invite_member_rejects_invalid_email(self) -> None:
        with self.assertRaisesRegex(ValidationError, "valid email"):
            MembershipService.invite_member(
                self.owner,
                self.project,
                "codex-invalid-email-no-at",
                "viewer",
            )

        self.assertFalse(
            ProjectInvitation.objects.filter(
                project=self.project,
                email="codex-invalid-email-no-at",
            ).exists()
        )
