from django.test import TestCase

from apps.projects.models import App, Project
from apps.projects.services import AppService
from apps.users.models import User


class AppServiceTests(TestCase):
    def setUp(self) -> None:
        self.owner = User.objects.create(email="owner@example.com")
        self.project = Project.objects.create(
            owner=self.owner,
            name="Demo Project",
            slug="demo-project",
        )

    def test_update_app_name_preserves_stable_slug(self) -> None:
        app = App.objects.create(
            project=self.project,
            name="Original App",
            slug="stable-app-id",
            framework=App.Framework.FASTAPI,
        )

        updated = AppService.update_app(
            self.project,
            "stable-app-id",
            name="Renamed App",
        )

        self.assertEqual(updated.name, "Renamed App")
        self.assertEqual(updated.slug, "stable-app-id")
        self.assertTrue(
            App.objects.filter(
                project=self.project,
                slug="stable-app-id",
                name="Renamed App",
            ).exists()
        )
