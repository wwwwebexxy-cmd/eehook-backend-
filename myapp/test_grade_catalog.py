from django.test import TestCase
from rest_framework.test import APIClient

from .models import Grade, User


class GradeCatalogApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_superuser(
            email="grade-admin@example.invalid",
            password="GradePass123!",
        )
        self.client.force_authenticate(user=self.admin)

    def test_grade_is_persisted_listed_and_hard_deleted(self):
        created = self.client.post(
            "/admin/manage/grades/",
            {"name": "  Flawless  "},
            format="json",
        )

        self.assertEqual(created.status_code, 201, created.data)
        grade_id = created.data["id"]
        self.assertEqual(created.data["name"], "Flawless")
        self.assertTrue(Grade.objects.filter(pk=grade_id, name="Flawless").exists())

        listed = self.client.get("/admin/manage/grades/")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.data["results"][0]["name"], "Flawless")

        deleted = self.client.delete(f"/admin/manage/grades/{grade_id}/")
        self.assertEqual(deleted.status_code, 204)
        self.assertFalse(Grade.objects.filter(pk=grade_id).exists())

    def test_grade_names_are_case_insensitively_unique(self):
        first = self.client.post(
            "/admin/manage/grades/",
            {"name": "A+"},
            format="json",
        )
        duplicate = self.client.post(
            "/admin/manage/grades/",
            {"name": "a+"},
            format="json",
        )

        self.assertEqual(first.status_code, 201, first.data)
        self.assertEqual(duplicate.status_code, 400, duplicate.data)
