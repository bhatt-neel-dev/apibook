from django.test import TestCase

from apps.projects.models import Project
from apps.projects.services import ProjectService
from apps.users.models import User


class ProjectServiceTests(TestCase):
    def setUp(self) -> None:
        self.owner = User.objects.create(email="owner@example.com")
        self.project = Project.objects.create(
            owner=self.owner,
            name="Original Project",
            slug="stable-project-id",
        )

    def test_update_project_name_preserves_stable_slug(self) -> None:
        updated = ProjectService.update_project(
            self.owner,
            "stable-project-id",
            name="Renamed Project",
        )

        self.assertEqual(updated.name, "Renamed Project")
        self.assertEqual(updated.slug, "stable-project-id")
        self.assertTrue(
            Project.objects.filter(
                id=self.project.id,
                slug="stable-project-id",
                name="Renamed Project",
            ).exists()
        )
