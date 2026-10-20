import io
import json
import tempfile
import sqlite3
from contextlib import closing
from unittest.mock import patch
from pathlib import Path
from zipfile import ZipFile
from PIL import Image
from pypdf import PdfWriter
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, SimpleTestCase, Client, override_settings
from .models import SiteSettings, ResearchDirection, Project, Member, Publication, Resource, Page
from .exporting import website_archive


@override_settings(ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"])
class WebsiteTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.media_settings = override_settings(MEDIA_ROOT=Path(cls.temporary.name) / "media")
        cls.media_settings.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls.media_settings.disable()
        cls.temporary.cleanup()

    @classmethod
    def setUpTestData(cls):
        call_command("seed_site", verbosity=0)
        cls.admin = get_user_model().objects.create_superuser("test-owner", password="Test-only-strong-password-2026")

    def login(self):
        self.client.force_login(self.admin, backend="django.contrib.auth.backends.ModelBackend")

    def member_data(self, **changes):
        data = {"name": "测试成员", "group": "students", "stage": "博士研究生", "school": "测试大学",
                "workplace": "", "cohort": "2026级", "bio": "", "position": 99, "is_published": "on"}
        data.update(changes)
        return data

    def test_seed_preserves_content_and_is_idempotent(self):
        self.assertEqual(Member.objects.count(), 49)
        self.assertEqual(Resource.objects.count(), 9)
        self.assertEqual(Project.objects.count(), 4)
        SiteSettings.objects.filter(pk=1).update(name="已修改名称")
        call_command("seed_site", verbosity=0)
        self.assertEqual(SiteSettings.objects.get(pk=1).name, "已修改名称")
        self.assertEqual(Member.objects.count(), 49)
        source = json.loads((settings.BASE_DIR / "seed/content.json").read_text(encoding="utf-8"))
        for item in source["research"]:
            self.assertContains(self.client.get("/research.html"), item["text"])
        for paragraph in source["leader"]["bio"]:
            self.assertContains(self.client.get("/team.html"), paragraph)

    def test_all_public_routes_and_hidden_admin(self):
        for slug, _ in Page.ROUTES:
            response = self.client.get(f"/{slug}.html")
            self.assertEqual(response.status_code, 200)
            self.assertNotContains(response, "/manage/")
            self.assertIn("object-src 'none'", response["Content-Security-Policy"])
        self.assertEqual(self.client.get("/manage/").status_code, 302)
        self.assertEqual(self.client.get("/manage/export/").status_code, 302)
        self.assertEqual(self.client.get("/admin/").status_code, 404)
        self.assertEqual(self.client.get("/data/site.sqlite3").status_code, 404)
        self.assertEqual(self.client.get("/media/../../secret.key").status_code, 404)
        self.assertEqual(self.client.get("/manage/login/")["X-Robots-Tag"], "noindex, nofollow, noarchive")

    def test_admin_crud_draft_visibility_and_order(self):
        self.login()
        result = self.client.post("/manage/catalog/member/add/", self.member_data())
        self.assertEqual(result.status_code, 302)
        member = Member.objects.get(name="测试成员")
        self.assertContains(self.client.get("/team.html"), "测试成员")
        result = self.client.post(f"/manage/catalog/member/{member.pk}/change/",
                                 self.member_data(name="更新姓名", edit_version=member.version, is_published=""))
        self.assertEqual(result.status_code, 302)
        self.assertNotContains(self.client.get("/team.html"), "更新姓名")
        self.assertNotContains(self.client.get("/team.html"), "测试成员")
        member.refresh_from_db()
        self.assertEqual(member.version, 2)
        self.assertFalse(member.is_published)
        response = self.client.post(f"/manage/catalog/member/{member.pk}/delete/", {"post": "yes"})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Member.objects.filter(pk=member.pk).exists())

    def test_stale_admin_form_cannot_overwrite_newer_change(self):
        self.login()
        member = Member.objects.create(name="原姓名", group="students", is_published=True)
        url = f"/manage/catalog/member/{member.pk}/change/"
        self.assertEqual(self.client.post(url, self.member_data(name="新内容", edit_version=1)).status_code, 302)
        response = self.client.post(url, self.member_data(name="过期内容", edit_version=1))
        self.assertContains(response, "已被另一个窗口修改")
        member.refresh_from_db()
        self.assertEqual(member.name, "新内容")

    def test_csrf_and_read_only_permissions(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin, backend="django.contrib.auth.backends.ModelBackend")
        self.assertEqual(client.post("/manage/catalog/member/add/", self.member_data()).status_code, 403)
        reader = get_user_model().objects.create_user("reader", is_staff=True)
        reader.user_permissions.add(Permission.objects.get(codename="view_member"))
        self.client.force_login(reader, backend="django.contrib.auth.backends.ModelBackend")
        self.assertEqual(self.client.get("/manage/catalog/member/").status_code, 200)
        self.assertEqual(self.client.post("/manage/catalog/member/add/", self.member_data()).status_code, 403)
        self.assertEqual(self.client.get("/manage/export/").status_code, 403)

    def test_image_upload_validation(self):
        self.login()
        fake = SimpleUploadedFile("fake.jpg", b"<script>alert(1)</script>", content_type="image/jpeg")
        response = self.client.post("/manage/catalog/member/add/", self.member_data(photo=fake))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Member.objects.filter(name="测试成员").exists())
        stream = io.BytesIO()
        Image.new("RGB", (20, 20), "blue").save(stream, format="PNG")
        image = SimpleUploadedFile("valid.png", stream.getvalue(), content_type="image/png")
        self.assertEqual(self.client.post("/manage/catalog/member/add/", self.member_data(photo=image)).status_code, 302)
        photo = Member.objects.get(name="测试成员").photo
        self.assertTrue(photo.name.startswith("uploads/"))
        self.assertEqual(self.client.get(photo.url).status_code, 200)

    def test_pdf_upload_and_invalid_file(self):
        self.login()
        values = {"title": "测试指南", "english": "", "kind": "指南", "disease": "测试方向",
                  "year": 2026, "version_label": "2026版", "journal": "测试来源", "position": 1, "is_published": "on"}
        fake = SimpleUploadedFile("fake.pdf", b"not pdf", content_type="application/pdf")
        response = self.client.post("/manage/catalog/resource/add/", {**values, "document": fake})
        self.assertContains(response, "有效的 PDF")
        self.assertFalse(Resource.objects.filter(title="测试指南").exists())
        file = io.BytesIO()
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=300)
        writer.write(file)
        pdf = SimpleUploadedFile("valid.pdf", file.getvalue(), content_type="application/pdf")
        self.assertEqual(self.client.post("/manage/catalog/resource/add/", {**values, "document": pdf}).status_code, 302)
        resource = Resource.objects.get(title="测试指南")
        self.assertEqual(resource.pages, 1)
        response = self.client.get(resource.document.url)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        response.close()
        self.assertContains(self.client.get("/resources.html"), 'value="测试方向"')

    def test_publication_edit_url_validation_and_escaping(self):
        self.login()
        values = {"kind": "paper", "title": "<script>alert(1)</script>", "authors": "Test Author", "year": 2026,
                  "journal": "Test Journal", "citation": "", "summary": "", "position": 1, "is_published": "on"}
        response = self.client.post("/manage/catalog/publication/add/", {**values, "url": "javascript:alert(1)"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Publication.objects.exists())
        self.assertEqual(self.client.post("/manage/catalog/publication/add/", {**values, "url": "https://example.org/paper"}).status_code, 302)
        response = self.client.get("/publications.html")
        self.assertContains(response, "&lt;script&gt;")
        self.assertNotContains(response, "<script>alert")
        self.assertContains(response, "https://example.org/paper")

    def test_empty_collections_render_and_export(self):
        for model in (Member, ResearchDirection, Project, Resource, Publication):
            model.objects.all().delete()
        for slug, _ in Page.ROUTES:
            self.assertEqual(self.client.get(f"/{slug}.html").status_code, 200)
        with website_archive() as stream, ZipFile(stream) as archive:
            self.assertIn("index.html", archive.namelist())

    def test_export_contains_only_public_content_and_assets(self):
        Member.objects.create(name="未公开成员", group="students", is_published=False)
        with website_archive() as stream, ZipFile(stream) as archive:
            names = archive.namelist()
            self.assertEqual(sum(name.endswith(".pdf") for name in names), 9)
            self.assertEqual(sum(name.endswith(".html") for name in names), 6)
            team = archive.read("team.html").decode()
            self.assertNotIn("未公开成员", team)
            self.assertNotIn("/manage/", team)
            self.assertNotIn("/static/", team)
            self.assertNotIn('src="/media/', team)
            self.assertFalse(any("sqlite" in name or "secret" in name for name in names))
            self.assertIsNone(archive.testzip())

    def test_login_lockout_after_five_failures(self):
        for _ in range(5):
            response = self.client.post("/manage/login/", {"username": "test-owner", "password": "incorrect"})
        self.assertEqual(response.status_code, 429)
        response = self.client.post("/manage/login/", {"username": "test-owner", "password": "Test-only-strong-password-2026"})
        self.assertEqual(response.status_code, 429)
        self.assertContains(response, "登录暂时锁定", status_code=429)


class BackupTests(SimpleTestCase):
    def test_backup_is_readable_and_closes_database_handles(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source.sqlite3"
            with closing(sqlite3.connect(source)) as db:
                db.execute("CREATE TABLE sample (value TEXT)")
                db.execute("INSERT INTO sample VALUES ('preserved')")
                db.commit()
            media = root / "media"
            media.mkdir()
            (media / "example.txt").write_text("asset")
            with override_settings(DATA_DIR=root, MEDIA_ROOT=media), patch.dict(settings.DATABASES["default"], {"NAME": str(source)}):
                call_command("backup_site", verbosity=0)
            archive = next((root / "backups").glob("*.zip"))
            with ZipFile(archive) as zipped:
                self.assertEqual(zipped.read("media/example.txt"), b"asset")
                restored = root / "restored.sqlite3"
                restored.write_bytes(zipped.read("site.sqlite3"))
            with closing(sqlite3.connect(restored)) as db:
                self.assertEqual(db.execute("SELECT value FROM sample").fetchone()[0], "preserved")
            # Windows will reject these deletions if a connection was left open.
            restored.unlink()
            source.unlink()
