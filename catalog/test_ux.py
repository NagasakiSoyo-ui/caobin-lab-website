import re
from contextlib import closing
from urllib.parse import quote
from zipfile import ZipFile
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.management import call_command
from django.test import TestCase, override_settings
from .exporting import check_links, readable_names, website_archive
from .models import Figure, Member, Project, Publication, ResearchDirection, Resource
from .test_research import MediaMixin


@override_settings(ALLOWED_HOSTS=["testserver"])
class UsabilityFixTests(MediaMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_site", verbosity=0)
        call_command("seed_publications", verbosity=0)
        cls.admin = get_user_model().objects.create_superuser("owner", password="Test-only-strong-password-2026")

    def login(self, user=None):
        self.client.force_login(user or self.admin, backend="django.contrib.auth.backends.ModelBackend")

    # --- resource PDF file names -------------------------------------------------------
    def test_resource_pdf_is_inline_with_title_file_name_and_original_bytes(self):
        resource = Resource.objects.get(document="initial/documents/resource-05.pdf")
        response = self.client.get(resource.document.url)
        self.assertEqual(response["Content-Type"], "application/pdf")
        expected = "inline; filename*=utf-8''" + quote(resource.title + ".pdf")
        self.assertEqual(response["Content-Disposition"], expected)
        self.assertNotIn("resource-05", response["Content-Disposition"])
        self.assertEqual(b"".join(response.streaming_content),
                         (settings.BASE_DIR / "seed/documents/resource-05.pdf").read_bytes())
        self.assertContains(self.client.get("/resources.html"), f'download="{resource.title}.pdf"')

    def test_unpublished_resource_and_images_keep_stored_file_name(self):
        resource = Resource.objects.get(document="initial/documents/resource-05.pdf")
        Resource.objects.filter(pk=resource.pk).update(is_published=False)
        with closing(self.client.get(resource.document.url)) as response:
            self.assertEqual(response["Content-Disposition"], 'inline; filename="resource-05.pdf"')
            self.assertNotIn(quote(resource.title), response["Content-Disposition"])
        figure = Figure.objects.exclude(image="").first()
        with closing(self.client.get(figure.image.url)) as image:
            self.assertEqual(image["Content-Disposition"], f'inline; filename="{figure.image.name.rsplit("/", 1)[-1]}"')

    def test_download_name_strips_characters_unsafe_in_file_names(self):
        resource = Resource(title=' 指南/共识: "2025" <修订>\\版? * | \n.')
        self.assertEqual(resource.download_name, "指南 共识 2025 修订 版.pdf")
        self.assertEqual(Resource(title="///").download_name, "document.pdf")
        self.assertEqual(Resource(title="长" * 500).download_name, "长" * 60 + ".pdf")
        nice = Resource.objects.get(document="initial/documents/resource-09.pdf")
        self.assertEqual(nice.download_name, nice.title.replace(":", " ").replace("  ", " ") + ".pdf")

    def test_offline_export_stores_each_pdf_once_under_its_title(self):
        with website_archive() as stream, ZipFile(stream) as archive:
            names = set(archive.namelist())
            pdfs = sorted(n for n in names if n.endswith(".pdf"))
            resources = archive.read("resources.html").decode()
            pages = {n: archive.read(n).decode() for n in names if n.endswith(".html")}
            for resource in Resource.objects.filter(is_published=True):
                path = "media/initial/documents/" + resource.download_name
                self.assertIn(path, names)
                self.assertEqual(archive.read(path), (settings.BASE_DIR / "seed" / resource.document.name.removeprefix("initial/")).read_bytes())
                self.assertIn(f'href="{quote(path)}"', resources)
        self.assertEqual(len(pdfs), 9)
        self.assertFalse(any(re.search(r"resource-\d+\.pdf$", n) for n in names))
        check_links(pages, names)

    def test_offline_names_are_unique_for_repeated_titles(self):
        first, second = Resource.objects.filter(is_published=True)[:2]
        second.title = first.title
        renamed = readable_names([first, second, first])
        self.assertEqual(sorted(renamed.values()), [f"media/initial/documents/{first.title} (2).pdf",
                                                     f"media/initial/documents/{first.title}.pdf"])

    def test_media_path_traversal_is_still_blocked(self):
        for path in ("/media/../secret.key", "/media/..%2Fsecret.key", "/media/initial/../../secret.key",
                     "/media/%2E%2E/site.sqlite3"):
            self.assertEqual(self.client.get(path).status_code, 404, path)

    def test_offline_names_do_not_collide_on_case_insensitive_filesystems(self):
        first, second = Resource.objects.filter(is_published=True)[:2]
        first.title, second.title = "Guideline", "GUIDELINE"
        renamed = readable_names([first, second])
        self.assertEqual(len({name.casefold() for name in renamed.values()}), 2)
        self.assertTrue(renamed[second.document.url].endswith("GUIDELINE (2).pdf"))

    # --- public display ------------------------------------------------------------------
    def test_direction_shortcuts_show_full_original_titles(self):
        html = self.client.get("/research.html").content.decode()
        jump = re.search(r'<nav class="direction-jump".*?</nav>', html, re.S).group(0)
        self.assertNotIn("…", jump)
        for direction in ResearchDirection.objects.filter(is_published=True):
            self.assertIn(f"{direction.title}</a>", jump)
            self.assertEqual(direction.label, direction.title)
        direction = ResearchDirection.objects.get(slug="microbiome")
        direction.short_title = "微生物组"
        self.assertEqual(direction.label, "微生物组")

    def test_publication_metadata_joins_only_present_fields(self):
        publication = Publication.objects.filter(is_published=True).first()

        def meta(**fields):
            Publication.objects.filter(pk=publication.pk).update(**fields)
            html = self.client.get("/publications.html").content.decode()
            article = re.search(rf'<article class="pub-entry"[^>]*>(?:(?!</article>).)*?{re.escape(publication.title)}.*?</article>',
                                html, re.S).group(0)
            found = re.search(r'<p class="pub-meta">(.*?)</p>', article, re.S)
            return found.group(1) if found else None

        year = publication.year
        self.assertEqual(meta(journal="", citation=""), str(year))
        self.assertEqual(meta(journal="", citation="12(3):45"), f"{year} · 12(3):45")
        self.assertEqual(meta(journal="Lancet", citation=""), f'<span lang="en">Lancet</span> · {year}')
        self.assertEqual(meta(journal="Lancet", citation="1"), f'<span lang="en">Lancet</span> · {year} · 1')

    def test_home_cards_without_journal_have_no_dangling_separator(self):
        publication = Publication.objects.filter(is_published=True).first()
        Publication.objects.filter(pk=publication.pk).update(journal="", citation="")
        html = self.client.get("/index.html").content.decode()
        self.assertIn(f'<p class="pub-meta">{publication.year}</p>', html)

    def test_publications_use_actual_years_and_preserve_full_authors(self):
        html = self.client.get("/publications.html").content.decode()
        expected = sorted(set(Publication.objects.filter(is_published=True).values_list("year", flat=True)), reverse=True)
        years = [int(y) for y in re.findall(r'data-publication-year="(\d+)"', html)]
        self.assertEqual(years, expected)
        self.assertEqual(html.count('class="pub-entry"'), Publication.objects.filter(is_published=True).count())
        for publication in Publication.objects.filter(is_published=True):
            self.assertIn(publication.authors, html)
        self.assertNotIn('featured', html)
        self.assertNotIn('成果详情', html)
        Publication.objects.update(is_published=False)
        empty = self.client.get("/publications.html")
        self.assertContains(empty, '成果目录整理中')
        self.assertNotContains(empty, 'data-publication-year=')

    def test_original_link_uses_verified_identifiers_without_inventing_url(self):
        publication = Publication(title="No source yet", year=2026)
        self.assertEqual(publication.original_url, "")
        publication.pmid = "12345"
        self.assertEqual(publication.original_url, "https://pubmed.ncbi.nlm.nih.gov/12345/")
        publication.doi = "10.1234/example"
        self.assertEqual(publication.original_url, "https://doi.org/10.1234/example")
        publication.url = "https://example.org/original"
        self.assertEqual(publication.original_url, publication.url)

    def test_member_without_photo_has_neutral_placeholder_without_repeating_name(self):
        member = Member.objects.filter(is_published=True, photo="").first()
        html = self.client.get("/team.html").content.decode()
        card = re.search(rf'<article class="member-card">(?:(?!</article>).)*?<h3>{re.escape(member.name)}</h3>.*?</article>',
                         html, re.S).group(0)
        self.assertIn('<span class="portrait-placeholder">暂无照片</span>', card)
        self.assertEqual(card.count(member.name), 1)

    # --- admin -------------------------------------------------------------------------
    def test_direction_relations_use_checkbox_lists_with_all_full_titles(self):
        self.login()
        draft = ResearchDirection.objects.create(title="未公开的研究方向用于关联测试", text="草稿", is_published=False)
        publication = Publication.objects.filter(is_published=True).first()
        figure = Figure.objects.first()
        for url in ("/manage/catalog/project/add/", f"/manage/catalog/publication/{publication.pk}/change/",
                    f"/manage/catalog/figure/{figure.pk}/change/"):
            html = self.client.get(url).content.decode()
            self.assertNotIn("selectfilter", html, url)
            self.assertNotIn("SelectFilter2.js", html, url)
            for direction in ResearchDirection.objects.all():
                self.assertRegex(html, rf'<input type="checkbox" name="directions" value="{direction.pk}"[^>]*>\s*{re.escape(direction.title)}')
            self.assertIn(draft.title, html)
        project = Project.objects.first()
        chosen = list(ResearchDirection.objects.filter(slug__in=["microbiome", "viral-sepsis"]).values_list("pk", flat=True)) + [draft.pk]
        data = {"title": project.title, "program": project.program, "dates": project.dates, "code": project.code,
                "position": project.position, "is_published": "on", "directions": chosen, "edit_version": project.version}
        self.assertEqual(self.client.post(f"/manage/catalog/project/{project.pk}/change/", data).status_code, 302)
        self.assertEqual(set(project.directions.values_list("pk", flat=True)), set(chosen))
        html = self.client.get(f"/manage/catalog/project/{project.pk}/change/").content.decode()
        for pk in chosen:
            self.assertRegex(html, rf'<input type="checkbox" name="directions" value="{pk}"[^>]*checked')
        self.assertNotContains(self.client.get("/projects.html"), draft.title)

    def test_change_form_has_return_link_respecting_permissions(self):
        self.login()
        member = Member.objects.first()
        for url in (f"/manage/catalog/member/{member.pk}/change/", "/manage/catalog/member/add/"):
            html = self.client.get(url).content.decode()
            self.assertEqual(html.count('class="closelink">返回列表（不保存）</a>'), 2, url)
            self.assertIn('href="/manage/catalog/member/"', html)
        reader = get_user_model().objects.create_user("reader", is_staff=True)
        reader.user_permissions.add(Permission.objects.get(codename="view_member"))
        self.login(reader)
        html = self.client.get(f"/manage/catalog/member/{member.pk}/change/").content.decode()
        self.assertNotIn("返回列表（不保存）", html)
        self.assertIn('class="closelink"', html)

    def test_member_form_loads_photo_preview_and_admin_pages_offer_export_feedback(self):
        self.login()
        member = Member.objects.exclude(photo="").first()
        html = self.client.get(f"/manage/catalog/member/{member.pk}/change/").content.decode()
        self.assertIn("admin-photo-preview.js", html)
        self.assertIn('id="photo-clear_id"', html)
        self.assertNotIn("admin-photo-preview.js", self.client.get("/manage/catalog/project/add/").content.decode())
        index = self.client.get("/manage/").content.decode()
        self.assertEqual(index.count('href="/manage/export/" data-export'), 2)
        self.assertIn('id="export-status" class="export-status" role="status"', index)
        self.assertIn("admin-export.js", index)
        self.client.logout()
        login = self.client.get("/manage/login/").content.decode()
        self.assertNotIn("admin-export.js", login)
        self.assertNotIn("export-status", login)
