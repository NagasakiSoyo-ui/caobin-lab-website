import io
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile
from PIL import Image
from django.contrib.auth import get_user_model
from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase, override_settings
from .exporting import check_links, localize, media_references, website_archive
from .models import Figure, Page, Project, Publication, PubMedCandidate, PubMedImportRun, ResearchDirection, SeedCheckpoint
from .pubmed import ImportFailure, accept
from datetime import timedelta
from django.utils import timezone

SEED_PMIDS = {"32311318", "40367638", "40858544", "38231624", "40693035"}


def pubmed_xml(*articles):
    """Minimal PubMed efetch XML. Each article: dict(pmid, doi, title, authors=[(last, fore, affiliation)])."""
    parts = []
    for a in articles:
        authors = "".join(
            f"<Author><LastName>{last}</LastName><ForeName>{fore}</ForeName><Initials>{fore[0]}</Initials>"
            + (f"<AffiliationInfo><Affiliation>{aff}</Affiliation></AffiliationInfo>" if aff else "") + "</Author>"
            for last, fore, aff in a["authors"])
        doi = f'<ArticleId IdType="doi">{a["doi"]}</ArticleId>' if a.get("doi") else ""
        parts.append(f"""<PubmedArticle><MedlineCitation><PMID>{a['pmid']}</PMID><Article>
<Journal><JournalIssue><Volume>10</Volume><Issue>1</Issue><PubDate>{'<Year>%s</Year>' % a.get('year', 2025) if a.get('year', 2025) else '<Season>Spring</Season>'}</PubDate></JournalIssue>
<Title>Test Journal</Title><ISOAbbreviation>Test J</ISOAbbreviation></Journal><ArticleTitle>{a['title']}</ArticleTitle>
<Pagination><MedlinePgn>1-9</MedlinePgn></Pagination><Abstract><AbstractText>Abstract.</AbstractText></Abstract>
<AuthorList>{authors}</AuthorList><PublicationTypeList><PublicationType>Journal Article</PublicationType></PublicationTypeList>
</Article></MedlineCitation><PubmedData><ArticleIdList><ArticleId IdType="pubmed">{a['pmid']}</ArticleId>{doi}</ArticleIdList></PubmedData></PubmedArticle>""")
    return ("<?xml version='1.0'?><PubmedArticleSet>" + "".join(parts) + "</PubmedArticleSet>").encode()


GROUP = ("Cao", "Bin", "National Center for Respiratory Medicine, China-Japan Friendship Hospital, Beijing, China.")
NAMESAKE = ("Cao", "Bin", "Department of Physics, Example University, Shanghai, China.")


def fake_ncbi(xml, ids=None):
    def _get(endpoint, params):
        if endpoint == "esearch.fcgi":
            return json.dumps({"esearchresult": {"idlist": ids or []}}).encode()
        return xml
    return patch("catalog.pubmed._get", side_effect=_get)


class MediaMixin:
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


@override_settings(ALLOWED_HOSTS=["testserver"])
class ResearchSiteTests(MediaMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_site", verbosity=0)
        call_command("seed_publications", verbosity=0)
        cls.admin = get_user_model().objects.create_superuser("owner", password="Test-only-strong-password-2026")

    def login(self, user=None):
        self.client.force_login(user or self.admin, backend="django.contrib.auth.backends.ModelBackend")

    def html_pages(self):
        with website_archive() as stream, ZipFile(stream) as archive:
            return {n: archive.read(n).decode() for n in archive.namelist() if n.endswith(".html")}, set(archive.namelist())

    # --- structure and content -------------------------------------------------------
    def test_seven_sections_and_original_content_preserved(self):
        index = self.client.get("/index.html")
        for slug, title in Page.ROUTES:
            self.assertContains(index, f'href="{slug}.html"')
        nav = index.content.decode().split('id="site-nav"')[1].split("</nav>")[0]
        self.assertEqual(nav.count("<a "), 7)
        for absent in ("动态", "新闻", "招聘"):
            self.assertNotIn(absent, nav)
        self.assertContains(index, 'href="projects.html"')
        projects = self.client.get("/projects.html")
        for project in Project.objects.all():
            for value in (project.title, project.program, project.code, project.dates):
                self.assertContains(projects, value)
        self.assertNotContains(self.client.get("/publications.html"), "2024ZD0522500")
        self.assertEqual(Project.objects.count(), 4)
        self.assertEqual(ResearchDirection.objects.count(), 6)
        self.assertContains(self.client.get("/contact.html"), "刘医生")

    def test_direction_details_have_stable_urls_full_text_and_relations(self):
        slugs = list(ResearchDirection.objects.values_list("slug", flat=True))
        self.assertEqual(slugs, ["viral-sepsis", "pathogen-diagnosis", "antiviral-evaluation",
                                 "real-world-evidence", "microbiome", "translation"])
        research = self.client.get("/research.html")
        for direction in ResearchDirection.objects.all():
            self.assertContains(research, f'href="research-{direction.slug}.html"')
            response = self.client.get(f"/research-{direction.slug}.html")
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, direction.text)
            self.assertIn("object-src 'none'", response["Content-Security-Policy"])
            figures = Figure.objects.filter(directions=direction, is_published=True)
            self.assertTrue(figures.exists(), direction.slug)
            self.assertTrue(all(f.kind == "original" and f.source_url for f in figures))
            self.assertContains(response, 'class="figure-plate"')
        viral = self.client.get("/research-viral-sepsis.html")
        self.assertContains(viral, "82530002")  # linked project
        self.assertContains(viral, "publication-2020-sars-cov-2-viral-sepsis.html")
        self.assertNotContains(self.client.get("/research-translation.html"), "direction-translation.svg")
        self.assertEqual(self.client.get("/research-unknown.html").status_code, 404)

    def test_seeded_publications_have_verified_metadata_and_figures(self):
        for pmid in SEED_PMIDS:
            publication = Publication.objects.get(pmid=pmid)
            self.assertTrue(publication.is_published and publication.doi)
            self.assertEqual(publication.summary, "")
            self.assertIn("单位匹配", publication.source_note)
        self.assertEqual(Publication.objects.get(pmid="40858544").doi, "10.1038/s41392-025-02365-x")
        with_figures = Publication.objects.filter(pmid__in=SEED_PMIDS, figures__is_published=True).distinct()
        self.assertEqual(with_figures.count(), 5)
        fig6 = Figure.objects.get(publication__pmid="40858544", label="Fig. 6")
        self.assertEqual((fig6.title, fig6.caption, fig6.license_note), (fig6.label, "", ""))
        self.assertEqual(fig6.source_url, "https://pmc.ncbi.nlm.nih.gov/articles/PMC12381301/figure/Fig6/")
        detail = self.client.get("/publication-2025-streptococcus-oralis-influenza.html")
        for text in ("https://pubmed.ncbi.nlm.nih.gov/40858544/", "https://doi.org/10.1038/s41392-025-02365-x",
                     "Fig. 6", "原文图页面", 'data-lightbox'):
            self.assertContains(detail, text)
        self.assertNotContains(detail, "中文概述")
        page = self.client.get("/publications.html")
        self.assertContains(page, "并非全部成果")
        self.assertNotContains(page, "完整全部成果")
        self.assertContains(page, 'id="pub-year"')
        # Non-featured publications are catalogue entries only, without a detail page.
        plain = Publication.objects.get(pmid="39775042")
        self.assertFalse(plain.has_detail)
        self.assertEqual(self.client.get(f"/{plain.page_name}").status_code, 404)

    def test_figure_link_works_without_javascript(self):
        figure = Figure.objects.get(publication__pmid="38231624", label="Figure 2")
        response = self.client.get("/publication-2024-oral-simnotrelvir-covid-19.html")
        self.assertContains(response, f'<a class="figure-zoom" href="{figure.image.url}"')
        image = self.client.get(figure.image.url)
        self.assertEqual(image["Content-Type"], "image/jpeg")
        image.close()

    # --- visibility: drafts and unpublished figures never leak -----------------------------
    def test_drafts_and_unpublished_figures_do_not_leak(self):
        direction = ResearchDirection.objects.get(slug="microbiome")
        draft_direction = ResearchDirection.objects.create(title="草稿方向甲", text="草稿方向正文", slug="draft-direction")
        draft_pub = Publication.objects.create(title="Draft Paper Beta", year=2026, pmid="99999991", is_featured=True,
                                               summary="草稿成果概述乙", slug="draft-paper")
        draft_pub.directions.add(direction)
        Project.objects.create(title="草稿课题丙", program="测试", dates="2026", is_published=False).directions.add(direction)
        hidden_fig = Figure.objects.create(publication=draft_pub, kind="original", label="Fig. 9", title="草稿成果配图丁",
                                           caption="说明", alt="草稿替代文字戊", credit="x", source_url="https://example.org/f",
                                           is_published=True, image=self.png("draft-figure.png"))
        hidden_fig.directions.add(direction)
        live_pub = Publication.objects.get(pmid="40858544")
        unpublished_fig = Figure.objects.create(publication=live_pub, kind="original", label="Fig. 2", title="未公开配图己",
                                                caption="说明", alt="未公开替代文字庚", credit="x",
                                                source_url="https://example.org/f", is_published=False,
                                                image=self.png("unpublished-figure.png"))
        unpublished_fig.directions.add(direction)
        secrets = ["草稿方向甲", "Draft Paper Beta", "草稿成果概述乙", "草稿课题丙", "草稿成果配图丁", "草稿替代文字戊",
                   "未公开配图己", "未公开替代文字庚", hidden_fig.image.name, unpublished_fig.image.name, "draft-direction", "draft-paper"]
        pages, names = self.html_pages()
        for name, html in pages.items():
            for secret in secrets:
                self.assertNotIn(secret, html, f"{secret} leaked into {name}")
        self.assertFalse(any(hidden_fig.image.name in n or unpublished_fig.image.name in n for n in names))
        for url in ("/research-draft-direction.html", "/publication-draft-paper.html"):
            self.assertEqual(self.client.get(url).status_code, 404)
        for url in ("/index.html", "/research.html", "/research-microbiome.html", "/publications.html", "/projects.html"):
            for secret in secrets:
                self.assertNotContains(self.client.get(url), secret)
        self.assertFalse(draft_direction.is_published)

    def test_unpublishing_publication_withdraws_its_figures(self):
        publication = Publication.objects.get(pmid="40858544")
        figure_url = publication.figures.first().image.url
        self.assertContains(self.client.get("/research-microbiome.html"), figure_url)
        Publication.objects.filter(pk=publication.pk).update(is_published=False)
        for url in ("/research-microbiome.html", "/publications.html", "/index.html"):
            self.assertNotContains(self.client.get(url), figure_url)
        self.assertEqual(self.client.get(f"/{publication.page_name}").status_code, 404)
        Publication.objects.filter(pk=publication.pk).update(is_published=True)
        Figure.objects.filter(publication=publication).update(is_published=False)
        self.assertNotContains(self.client.get(f"/{publication.page_name}"), figure_url)
        # Featured cards require a public figure, so no empty figure frame is rendered.
        self.assertNotContains(self.client.get("/publications.html"), f'href="{publication.page_name}" tabindex="-1"')

    # --- export -------------------------------------------------------------------------
    def test_export_contains_all_public_detail_pages_and_valid_links(self):
        Publication.objects.filter(pmid="39775042").update(url="https://example.org/media/paper.pdf")
        pages, names = self.html_pages()
        for direction in ResearchDirection.objects.all():
            self.assertIn(direction.page_name, pages)
        featured = [p.page_name for p in Publication.objects.filter(is_featured=True, is_published=True)]
        self.assertEqual(len(featured), 7)
        for name in featured:
            self.assertIn(name, pages)
        for figure in Figure.objects.filter(is_published=True).exclude(image=""):
            self.assertIn("media/" + figure.image.name, names)
        self.assertNotIn("assets/figures/direction-translation.svg", names)
        self.assertNotIn("assets/favicon.svg", names)
        self.assertEqual(sum(n.endswith(".pdf") for n in names), 9)
        self.assertEqual(sum("/people/" in n for n in names), 40)
        for html in pages.values():
            self.assertNotIn('="/media/', html)
            self.assertNotIn('="/static/', html)
            self.assertNotIn("/manage/", html)
        # External URLs containing /media/ are not rewritten by the export.
        self.assertIn("https://example.org/media/paper.pdf", pages["publications.html"])
        check_links(pages, names)  # re-run explicitly: raises on any broken internal link

    def test_link_checker_reports_missing_files_and_anchors(self):
        with self.assertRaisesMessage(ValueError, "缺少 missing.html"):
            check_links({"a.html": '<a href="missing.html">x</a>'}, {"a.html"})
        with self.assertRaisesMessage(ValueError, "没有锚点"):
            check_links({"a.html": '<a href="b.html#nope">x</a>', "b.html": "<p id='yes'></p>"}, {"a.html", "b.html"})
        with self.assertRaisesMessage(ValueError, "非离线路径"):
            check_links({"a.html": '<img src="/media/x.jpg">'}, {"a.html"})

    def test_empty_research_content_renders_and_exports(self):
        Figure.objects.all().delete()
        Publication.objects.all().delete()
        Project.objects.all().delete()
        for url in ("/publications.html", "/projects.html", "/research.html", "/index.html", "/research-microbiome.html"):
            self.assertEqual(self.client.get(url).status_code, 200)
        self.assertContains(self.client.get("/publications.html"), "成果目录整理中")
        pages, _ = self.html_pages()
        self.assertNotIn('class="figure-plate"', pages["research-microbiome.html"])

    # --- seed idempotency ------------------------------------------------------------------
    def test_seed_publications_is_idempotent_and_keeps_manual_edits(self):
        publication = Publication.objects.get(pmid="38231624")
        Publication.objects.filter(pk=publication.pk).update(summary="人工修改的中文概述", is_published=False, slug="manual-slug")
        Figure.objects.filter(publication=publication, label="Figure 1").delete()
        ResearchDirection.objects.filter(slug="microbiome").update(summary="人工方向简介")
        counts = (Publication.objects.count(), Figure.objects.count())
        call_command("seed_publications", verbosity=0)
        publication.refresh_from_db()
        self.assertEqual((publication.summary, publication.is_published, publication.slug),
                         ("人工修改的中文概述", False, "manual-slug"))
        self.assertEqual((Publication.objects.count(), Figure.objects.count()), (counts[0], counts[1]))
        self.assertEqual(ResearchDirection.objects.get(slug="microbiome").summary, "人工方向简介")

    def test_seed_runs_once_and_never_restores_removed_or_cleared_content(self):
        self.assertEqual(SeedCheckpoint.objects.count(), 1)
        lancet = Publication.objects.get(pmid="32311318")
        lancet.figures.all().delete()  # removes the last (only) figure of this paper
        Publication.objects.filter(pk=lancet.pk).update(summary="")
        Publication.objects.get(pmid="40858544").directions.clear()
        Publication.objects.filter(pmid="40367638").delete()
        ResearchDirection.objects.filter(slug="microbiome").update(summary="")
        Project.objects.get(code="82530002").directions.clear()
        snapshot = lambda: (Publication.objects.count(), Figure.objects.count(),
                            Publication.objects.get(pk=lancet.pk).summary,
                            Publication.objects.get(pmid="40858544").directions.count(),
                            ResearchDirection.objects.get(slug="microbiome").summary,
                            Project.objects.get(code="82530002").directions.count())
        before = snapshot()
        for _ in range(2):  # every start of setup_local.py runs both seed commands
            out = io.StringIO()
            call_command("seed_site", stdout=io.StringIO())
            call_command("seed_publications", stdout=out)
            self.assertIn("跳过", out.getvalue())
        self.assertEqual(snapshot(), before)
        self.assertEqual(before[2:], ("", 0, "", 0))
        self.assertFalse(Publication.objects.filter(pmid="40367638").exists())
        self.assertFalse(lancet.figures.exists())

    def test_explicit_refill_is_the_only_way_to_restore_seed_content(self):
        Publication.objects.get(pmid="32311318").figures.all().delete()
        call_command("seed_publications", stdout=io.StringIO())
        self.assertFalse(Publication.objects.get(pmid="32311318").figures.exists())
        call_command("seed_publications", "--refill", stdout=io.StringIO())
        self.assertTrue(Publication.objects.get(pmid="32311318").figures.exists())
        self.assertEqual(SeedCheckpoint.objects.count(), 1)

    def test_seed_reports_pmid_doi_conflict_without_merging(self):
        Publication.objects.filter(pmid="40858544").update(pmid=None)
        Publication.objects.create(title="Another record", year=2025, pmid="40858544", is_published=False)
        err = io.StringIO()
        # Explicit maintenance refill; the normal command is a no-op once initialized.
        call_command("seed_publications", "--refill", stderr=err, stdout=io.StringIO())
        self.assertIn("冲突", err.getvalue())
        self.assertEqual(Publication.objects.filter(title="Another record").count(), 1)
        self.assertIsNone(Publication.objects.get(doi="10.1038/s41392-025-02365-x").pmid)

    # --- admin ------------------------------------------------------------------------------
    def png(self, name="figure.png"):
        stream = io.BytesIO()
        Image.new("RGB", (40, 30), "navy").save(stream, format="PNG")
        return SimpleUploadedFile(name, stream.getvalue(), content_type="image/png")

    def figure_data(self, **changes):
        data = {"kind": "original", "publication": Publication.objects.get(pmid="40858544").pk, "label": "Fig. 3",
                "title": "新配图", "caption": "说明", "alt": "替代文字", "credit": "Zou X, et al.",
                "source_url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC12381301/figure/Fig3/", "license_note": "CC BY 4.0",
                "position": 5, "is_published": "on"}
        data.update(changes)
        return data

    def test_admin_figure_upload_rejects_svg_and_requires_source(self):
        self.login()
        svg = SimpleUploadedFile("x.svg", b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>",
                                 content_type="image/svg+xml")
        self.assertEqual(self.client.post("/manage/catalog/figure/add/", self.figure_data(image=svg)).status_code, 200)
        response = self.client.post("/manage/catalog/figure/add/", self.figure_data(image=self.png(), source_url=""))
        self.assertContains(response, "原图来源链接")
        self.assertFalse(Figure.objects.filter(title="新配图").exists())
        self.assertEqual(self.client.post("/manage/catalog/figure/add/", self.figure_data(image=self.png())).status_code, 302)
        figure = Figure.objects.get(title="新配图")
        self.assertTrue(figure.image.name.startswith("uploads/"))
        with self.assertRaises(ValidationError):
            Figure(kind="schematic", title="t", caption="c", alt="a").full_clean()

    def test_admin_figure_replacement_and_stale_edit_conflict(self):
        self.login()
        figure = Figure.objects.get(publication__pmid="40858544", label="Fig. 6")
        url = f"/manage/catalog/figure/{figure.pk}/change/"
        data = self.figure_data(label="Fig. 6", title=figure.title, publication=figure.publication_id,
                                source_url=figure.source_url, edit_version=figure.version,
                                directions=[d.pk for d in figure.directions.all()])
        self.assertEqual(self.client.post(url, {**data, "image": self.png("replacement.png")}).status_code, 302)
        figure.refresh_from_db()
        self.assertTrue(figure.image.name.startswith("uploads/"))
        self.assertContains(self.client.get("/research-microbiome.html"), figure.image.url)
        stale = self.client.post(url, {**data, "title": "过期修改"})
        self.assertContains(stale, "已被另一个窗口修改")
        figure.refresh_from_db()
        self.assertNotEqual(figure.title, "过期修改")

    def test_slug_is_frozen_after_creation(self):
        self.login()
        direction = ResearchDirection.objects.get(slug="microbiome")
        data = {"title": "呼吸道微生物组研究（新标题）", "short_title": direction.short_title, "summary": direction.summary,
                "text": direction.text, "slug": "changed", "position": direction.position, "is_published": "on",
                "covers_pathogen": "on", "edit_version": direction.version}
        self.assertEqual(self.client.post(f"/manage/catalog/researchdirection/{direction.pk}/change/", data).status_code, 302)
        direction.refresh_from_db()
        self.assertEqual((direction.slug, direction.title), ("microbiome", "呼吸道微生物组研究（新标题）"))
        self.assertEqual(self.client.get("/research-microbiome.html").status_code, 200)

    def test_project_direction_relation_editable_in_admin(self):
        self.login()
        project = Project.objects.get(code="82530002")
        direction = ResearchDirection.objects.get(slug="antiviral-evaluation")
        data = {"title": project.title, "program": project.program, "dates": project.dates, "code": project.code,
                "position": project.position, "is_published": "on", "directions": [direction.pk], "edit_version": project.version}
        self.assertEqual(self.client.post(f"/manage/catalog/project/{project.pk}/change/", data).status_code, 302)
        self.assertContains(self.client.get("/research-antiviral-evaluation.html"), project.title)
        self.assertNotContains(self.client.get("/research-viral-sepsis.html"), project.title)

    def test_srcset_urls_are_each_collected_and_rewritten(self):
        html = ('<img src="/static/site/x.svg" srcset="/media/a.jpg 1x, /media/a%402x.jpg 2x, '
                'https://example.org/media/b.jpg 3x"><a href="https://example.org/static/site/c.css">c</a>')
        self.assertEqual(media_references(html), {"/media/a.jpg", "/media/a@2x.jpg"})
        local = localize(html)
        self.assertIn('srcset="media/a.jpg 1x, media/a%402x.jpg 2x, https://example.org/media/b.jpg 3x"', local)
        self.assertIn('src="assets/x.svg"', local)
        self.assertIn('href="https://example.org/static/site/c.css"', local)
        check_links({"p.html": local}, {"p.html", "assets/x.svg", "media/a.jpg", "media/a@2x.jpg"})
        with self.assertRaisesMessage(ValueError, "缺少 media/a@2x.jpg"):
            check_links({"p.html": local}, {"p.html", "assets/x.svg", "media/a.jpg"})

    def test_figure_bulk_actions_refresh_timestamp_version_and_log(self):
        self.login()
        figures = list(Figure.objects.filter(publication__pmid="40858544"))
        old = timezone.now() - timedelta(days=3)
        Figure.objects.filter(pk__in=[f.pk for f in figures]).update(updated_at=old)
        response = self.client.post("/manage/catalog/figure/", {"action": "unpublish", "_selected_action": [f.pk for f in figures]})
        self.assertEqual(response.status_code, 302)
        for figure in figures:
            fresh = Figure.objects.get(pk=figure.pk)
            self.assertFalse(fresh.is_published)
            self.assertEqual(fresh.version, figure.version + 1)
            self.assertGreater(fresh.updated_at, old)
            self.assertTrue(LogEntry.objects.filter(object_id=str(figure.pk), change_message__contains="取消公开").exists())
        self.assertNotContains(self.client.get("/research-microbiome.html"), figures[0].image.url)
        # Re-running on already unpublished figures changes nothing and logs nothing.
        count = LogEntry.objects.count()
        self.client.post("/manage/catalog/figure/", {"action": "unpublish", "_selected_action": [f.pk for f in figures]})
        self.assertEqual(LogEntry.objects.count(), count)
        self.assertEqual(Figure.objects.get(pk=figures[0].pk).version, figures[0].version + 1)



class SeedInitializationTests(MediaMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_site", verbosity=0)

    def test_first_import_failure_rolls_back_and_can_be_retried(self):
        from catalog.management.commands import seed_publications
        original, calls = seed_publications.Command.copy_asset, []

        def flaky(command, relative):
            calls.append(relative)
            if len(calls) == 4:
                raise CommandError(f"初始素材缺失：{relative}")
            return original(command, relative)

        with patch.object(seed_publications.Command, "copy_asset", flaky), self.assertRaises(CommandError):
            call_command("seed_publications", stdout=io.StringIO())
        self.assertEqual((Publication.objects.count(), Figure.objects.count(), SeedCheckpoint.objects.count()), (0, 0, 0))
        call_command("seed_publications", stdout=io.StringIO())
        self.assertEqual(Publication.objects.count(), 11)
        self.assertEqual(Figure.objects.count(), 11)
        self.assertEqual(SeedCheckpoint.objects.get().key, "research-publications-v1")
        self.assertEqual(Publication.objects.filter(pmid__in=SEED_PMIDS, is_published=True).count(), 5)


@override_settings(ALLOWED_HOSTS=["testserver"])
class PubMedImportTests(MediaMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_site", verbosity=0)
        cls.admin = get_user_model().objects.create_superuser("owner", password="Test-only-strong-password-2026")

    def articles(self, title="Original Title"):
        return pubmed_xml(
            {"pmid": "111", "doi": "10.1000/ABC.1", "title": title, "authors": [("Li", "Hui", "X"), GROUP]},
            {"pmid": "222", "doi": "10.1000/xyz.2", "title": "Namesake paper", "authors": [NAMESAKE]},
        )

    def test_import_records_identity_evidence_and_is_idempotent(self):
        with fake_ncbi(self.articles(), ids=["111", "222"]):
            call_command("import_pubmed", stdout=io.StringIO())
        group, namesake = PubMedCandidate.objects.get(pmid="111"), PubMedCandidate.objects.get(pmid="222")
        self.assertEqual((group.identity_status, namesake.identity_status), ("matched", "unmatched"))
        self.assertIn("作者位置 2/2", group.identity_evidence)
        self.assertEqual(group.doi, "10.1000/abc.1")
        self.assertIn("NCBI PubMed E-utilities", group.query)
        PubMedCandidate.objects.filter(pk=namesake.pk).update(decision="rejected", decision_note="同名不同人")
        with fake_ncbi(self.articles(), ids=["111", "222"]):
            call_command("import_pubmed", stdout=io.StringIO())
        self.assertEqual(PubMedCandidate.objects.count(), 2)
        namesake.refresh_from_db()
        self.assertEqual((namesake.decision, namesake.decision_note), ("rejected", "同名不同人"))
        self.assertEqual(PubMedImportRun.objects.filter(status="ok").count(), 2)
        self.assertFalse(Publication.objects.exists())  # import never creates or publishes content

    def test_accept_creates_unpublished_draft_and_reimport_keeps_manual_edits(self):
        with fake_ncbi(self.articles(), ids=["111"]):
            call_command("import_pubmed", "--pmid", "111", stdout=io.StringIO())
        publication = accept(PubMedCandidate.objects.get(pmid="111"), self.admin)
        self.assertFalse(publication.is_published)
        self.assertEqual(publication.lab_role, "unverified")  # last author is never auto-marked corresponding
        self.assertNotContains(self.client.get("/publications.html"), "Original Title")
        Publication.objects.filter(pk=publication.pk).update(summary="人工中文概述", title="人工修订题目")
        slug = Publication.objects.get(pk=publication.pk).slug
        with fake_ncbi(self.articles(title="Changed Upstream Title"), ids=["111"]):
            call_command("import_pubmed", "--pmid", "111", stdout=io.StringIO())
        publication.refresh_from_db()
        self.assertEqual((publication.summary, publication.title, publication.slug), ("人工中文概述", "人工修订题目", slug))
        candidate = PubMedCandidate.objects.get(pmid="111")
        self.assertEqual(candidate.decision, "accepted")
        self.assertIn("Changed Upstream Title", candidate.upstream_changes)
        self.assertEqual(accept(candidate, self.admin).pk, publication.pk)  # repeat accept does not duplicate
        self.assertEqual(Publication.objects.count(), 1)

    def test_pmid_and_doi_matching_different_publications_is_a_conflict(self):
        a = Publication.objects.create(title="Paper A", year=2024, pmid="111")
        b = Publication.objects.create(title="Paper B", year=2024, doi="https://doi.org/10.1000/ABC.1")
        self.assertEqual(b.doi, "10.1000/abc.1")
        with fake_ncbi(self.articles(), ids=["111"]):
            call_command("import_pubmed", "--pmid", "111", stdout=io.StringIO())
        candidate = PubMedCandidate.objects.get(pmid="111")
        self.assertIn("冲突", candidate.conflict)
        with self.assertRaises(ImportFailure):
            accept(candidate, self.admin)
        self.login()
        response = self.client.post("/manage/catalog/pubmedcandidate/", {"action": "accept_selected", "_selected_action": [candidate.pk]}, follow=True)
        self.assertContains(response, "未自动合并")
        a.refresh_from_db(), b.refresh_from_db()
        self.assertEqual((a.doi, b.pmid), (None, None))
        self.assertEqual(Publication.objects.count(), 2)

    def test_admin_accept_action_and_permissions(self):
        with fake_ncbi(self.articles(), ids=["111", "222"]):
            call_command("import_pubmed", stdout=io.StringIO())
        reviewer = get_user_model().objects.create_user("reviewer", is_staff=True)
        reviewer.user_permissions.add(Permission.objects.get(codename="view_pubmedcandidate"))
        self.client.force_login(reviewer, backend="django.contrib.auth.backends.ModelBackend")
        self.assertEqual(self.client.get("/manage/catalog/pubmedcandidate/").status_code, 200)
        candidate = PubMedCandidate.objects.get(pmid="111")
        self.client.post("/manage/catalog/pubmedcandidate/", {"action": "accept_selected", "_selected_action": [candidate.pk]})
        self.assertFalse(Publication.objects.exists())
        self.assertEqual(self.client.get("/manage/catalog/pubmedcandidate/add/").status_code, 403)
        self.login()
        self.client.post("/manage/catalog/pubmedcandidate/", {"action": "accept_selected", "_selected_action": [candidate.pk]})
        self.assertEqual(Publication.objects.get().pmid, "111")
        rejected = PubMedCandidate.objects.get(pmid="222")
        self.client.post("/manage/catalog/pubmedcandidate/", {"action": "reject_selected", "_selected_action": [rejected.pk]})
        rejected.refresh_from_db()
        self.assertEqual(rejected.decision, "rejected")
        with self.assertRaises(ImportFailure):
            accept(rejected, self.admin)

    def login(self):
        self.client.force_login(self.admin, backend="django.contrib.auth.backends.ModelBackend")

    def action(self, name, *candidates):
        return self.client.post("/manage/catalog/pubmedcandidate/",
                                {"action": name, "_selected_action": [c.pk for c in candidates]})

    def test_rejection_can_be_reset_to_pending_with_audit(self):
        with fake_ncbi(self.articles(), ids=["111", "222"]):
            call_command("import_pubmed", stdout=io.StringIO())
        rejected, linked = PubMedCandidate.objects.get(pmid="222"), PubMedCandidate.objects.get(pmid="111")
        self.login()
        self.action("accept_selected", linked)
        self.action("reject_selected", rejected)
        rejected.refresh_from_db()
        self.assertEqual(rejected.decision, "rejected")
        with self.assertRaises(ImportFailure):
            accept(rejected, self.admin)
        # A view-only reviewer cannot undo the decision.
        reviewer = get_user_model().objects.create_user("viewer", is_staff=True)
        reviewer.user_permissions.add(Permission.objects.get(codename="view_pubmedcandidate"))
        self.client.force_login(reviewer, backend="django.contrib.auth.backends.ModelBackend")
        self.action("reset_selected", rejected)
        self.assertEqual(PubMedCandidate.objects.get(pk=rejected.pk).decision, "rejected")
        self.login()
        version = PubMedCandidate.objects.get(pk=rejected.pk).version
        linked_state = PubMedCandidate.objects.filter(pk=linked.pk).values("decision", "publication", "version").get()
        self.action("reset_selected", rejected, linked)
        rejected.refresh_from_db()
        self.assertEqual((rejected.decision, rejected.version, rejected.decided_by), ("pending", version + 1, self.admin))
        self.assertIn("恢复为待审核", rejected.decision_note)
        self.assertTrue(LogEntry.objects.filter(object_id=str(rejected.pk), change_message__contains="恢复为待审核").exists())
        self.assertEqual(PubMedCandidate.objects.filter(pk=linked.pk).values("decision", "publication", "version").get(), linked_state)
        # A re-import keeps the restored decision; the candidate can now be accepted.
        with fake_ncbi(self.articles(), ids=["222"]):
            call_command("import_pubmed", "--pmid", "222", stdout=io.StringIO())
        self.assertEqual(PubMedCandidate.objects.get(pk=rejected.pk).decision, "pending")
        self.assertEqual(accept(rejected, self.admin).pmid, "222")

    def test_missing_year_requires_verified_manual_year(self):
        xml = pubmed_xml({"pmid": "555", "doi": "10.1000/noyear", "title": "No Year", "year": None, "authors": [GROUP]})
        with fake_ncbi(xml, ids=["555"]):
            call_command("import_pubmed", "--pmid", "555", stdout=io.StringIO())
        candidate = PubMedCandidate.objects.get(pmid="555")
        self.assertIsNone(candidate.year)
        with self.assertRaisesMessage(ImportFailure, "缺少出版年份"):
            accept(candidate, self.admin)
        self.assertFalse(Publication.objects.exists())
        self.login()
        response = self.action("accept_selected", candidate)
        self.assertFalse(Publication.objects.exists())
        url = f"/manage/catalog/pubmedcandidate/{candidate.pk}/change/"
        self.assertContains(self.client.get(url), 'name="year"')
        bad = self.client.post(url, {"year": "1800", "decision_note": "", "edit_version": candidate.version})
        self.assertEqual(bad.status_code, 200)
        saved = self.client.post(url, {"year": "2023", "decision_note": "年份依据期刊官网核对", "edit_version": candidate.version})
        self.assertEqual(saved.status_code, 302)
        self.assertTrue(LogEntry.objects.filter(object_id=str(candidate.pk)).exists())
        with fake_ncbi(xml, ids=["555"]):
            call_command("import_pubmed", "--pmid", "555", stdout=io.StringIO())
        candidate.refresh_from_db()
        self.assertEqual(candidate.year, 2023)  # re-import does not erase the verified year
        self.assertEqual(accept(candidate, self.admin).year, 2023)
        self.assertNotContains(self.client.get(url), 'name="year"')  # locked once linked

    def test_linked_candidate_conflicts_when_identifiers_are_reassigned(self):
        with fake_ncbi(self.articles(), ids=["111"]):
            call_command("import_pubmed", "--pmid", "111", stdout=io.StringIO())
        candidate = PubMedCandidate.objects.get(pmid="111")
        first = accept(candidate, self.admin)
        # The PMID now belongs to a different publication: the old link must not be reused.
        Publication.objects.filter(pk=first.pk).update(pmid="999", doi=None)
        other = Publication.objects.create(title="Other", year=2024, pmid="111")
        with fake_ncbi(self.articles(), ids=["111"]):
            call_command("import_pubmed", "--pmid", "111", stdout=io.StringIO())
        candidate.refresh_from_db()
        self.assertIn(f"另一成果 #{other.pk}", candidate.conflict)
        with self.assertRaisesMessage(ImportFailure, "未沿用旧关联"):
            accept(candidate, self.admin)
        # The linked publication's DOI was edited to another value (no second record involved).
        other.delete()
        Publication.objects.filter(pk=first.pk).update(pmid="111", doi="10.1000/changed")
        with self.assertRaisesMessage(ImportFailure, "不一致"):
            accept(candidate, self.admin)
        first.refresh_from_db()
        self.assertEqual((first.pmid, first.doi), ("111", "10.1000/changed"))
        Publication.objects.filter(pk=first.pk).update(doi="10.1000/abc.1")
        self.assertEqual(accept(candidate, self.admin).pk, first.pk)

    def test_empty_result_and_network_failure_are_reported(self):
        with fake_ncbi(b"", ids=[]), self.assertRaisesMessage(CommandError, "检索结果为空"):
            call_command("import_pubmed", stdout=io.StringIO())
        with fake_ncbi(pubmed_xml(), ids=["333"]), self.assertRaisesMessage(CommandError, "未返回任何记录"):
            call_command("import_pubmed", stdout=io.StringIO())
        with patch("catalog.pubmed._get", side_effect=ImportFailure("无法连接 NCBI：timed out")), \
                self.assertRaisesMessage(CommandError, "无法连接 NCBI"):
            call_command("import_pubmed", stdout=io.StringIO())
        with fake_ncbi(b"<not-xml", ids=["444"]), self.assertRaisesMessage(CommandError, "无法解析"):
            call_command("import_pubmed", stdout=io.StringIO())
        statuses = list(PubMedImportRun.objects.order_by("started_at", "pk").values_list("status", flat=True))
        self.assertEqual(statuses, ["empty", "empty", "failed", "failed"])
        self.assertFalse(PubMedCandidate.objects.exists())


class LegacyMigrationTests(TransactionTestCase):
    """Upgrade a database at migration 0001 (the previously shipped schema) without data loss."""

    def test_content_cleanup_removes_known_defaults_but_preserves_human_edits(self):
        executor = MigrationExecutor(connection)
        executor.migrate([("catalog", "0004_seed_checkpoint")])
        old = executor.loader.project_state([("catalog", "0004_seed_checkpoint")]).apps
        OldPage = old.get_model("catalog", "Page")
        OldPage.objects.create(slug="research", title="研究方向", intro="围绕呼吸道感染的临床问题，连接病原、宿主与转化研究。")
        OldPage.objects.create(slug="contact", title="团队自定名称", intro="由团队撰写的联系介绍", version=7)
        OldFigure = old.get_model("catalog", "Figure")
        OldFigure.objects.create(title="旧示意图", static_asset="direction-translation.svg", kind="schematic")
        original = OldFigure.objects.create(title="团队图片标题", caption="团队提供的说明", image="initial/figures/pmid38231624-fig2.jpg", version=9)
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes("catalog"))
        self.assertEqual(Page.objects.get(slug="research").intro, "")
        manual = Page.objects.get(slug="contact")
        self.assertEqual((manual.title, manual.intro, manual.version), ("团队自定名称", "由团队撰写的联系介绍", 7))
        self.assertEqual(Figure.objects.count(), 1)
        figure = Figure.objects.get(pk=original.pk)
        self.assertEqual((figure.title, figure.caption, figure.version), ("团队图片标题", "团队提供的说明", 9))
        self.assertEqual(figure.image.name, original.image.name)

    def test_upgrade_backfills_stable_slugs_and_keeps_edits(self):
        executor = MigrationExecutor(connection)
        executor.migrate([("catalog", "0001_initial")])
        old = executor.loader.project_state([("catalog", "0001_initial")]).apps
        Page = old.get_model("catalog", "Page")
        for slug, title, en, intro in [("index", "首页", "Home", ""), ("research", "研究方向", "Research", ""),
                                       ("publications", "研究成果", "Publications", "科研项目、研究论文与其他科研成果。"),
                                       ("team", "研究团队", "Our Team", ""), ("resources", "学习资料", "Learning Resources", ""),
                                       ("contact", "联系我们", "Contact", "")]:
            Page.objects.create(slug=slug, title=title, english=en, intro=intro)
        Direction = old.get_model("catalog", "ResearchDirection")
        titles = ["病毒性肺炎与病毒性感染中毒症（viral sepsis）", "呼吸道病原体与精准感染诊断", "抗病毒药物临床评价与新药转化",
                  "急性呼吸道感染的真实世界临床研究", "呼吸道微生物组研究", "临床转化方向", "Custom Direction", "自定义方向"]
        for i, title in enumerate(titles):
            Direction.objects.create(title=title, text=f"人工编辑正文{i}", position=i, is_published=True, version=3)
        old.get_model("catalog", "Publication").objects.create(title="人工录入成果", year=2020, is_published=True)
        old.get_model("catalog", "Publication").objects.create(title="人工录入成果", year=2020, is_published=True)

        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes("catalog"))
        directions = list(ResearchDirection.objects.order_by("position"))
        self.assertEqual([d.slug for d in directions], ["viral-sepsis", "pathogen-diagnosis", "antiviral-evaluation",
                                                        "real-world-evidence", "microbiome", "translation",
                                                        "custom-direction", "direction-8"])
        self.assertEqual([d.text for d in directions], [f"人工编辑正文{i}" for i in range(8)])
        self.assertEqual([d.version for d in directions], [4] * 6 + [3] * 2)
        self.assertTrue(all(not d.short_title for d in directions[:6]))
        self.assertTrue(directions[0].covers_host and not directions[2].covers_pathogen)
        slugs = list(Publication.objects.values_list("slug", flat=True))
        self.assertEqual(len(set(slugs)), 2)
        self.assertTrue(all(slugs))
        self.assertEqual(Page.objects.get(slug="contact").title, "联系我们")
        self.assertTrue(Page.objects.filter(slug="projects").exists())
        self.assertEqual(Page.objects.get(slug="publications").intro, "")
        # A database from before the research release has no checkpoint and is imported once.
        self.assertFalse(SeedCheckpoint.objects.exists())
        with tempfile.TemporaryDirectory() as media, override_settings(MEDIA_ROOT=media):
            call_command("seed_publications", stdout=io.StringIO())
            self.assertEqual(Publication.objects.exclude(pmid=None).count(), 11)
            self.assertEqual(Publication.objects.filter(title="人工录入成果").count(), 2)
            Publication.objects.filter(pmid="32311318").delete()
            call_command("seed_publications", stdout=io.StringIO())
            self.assertFalse(Publication.objects.filter(pmid="32311318").exists())

    def test_database_seeded_before_checkpoint_is_marked_done(self):
        executor = MigrationExecutor(connection)
        executor.migrate([("catalog", "0003_candidate_year_validation")])
        old = executor.loader.project_state([("catalog", "0003_candidate_year_validation")]).apps
        old.get_model("catalog", "Figure").objects.create(
            kind="original", title="已导入的首批原图", caption="c", alt="a", image="initial/figures/pmid38231624-fig2.jpg",
            is_published=False)
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes("catalog"))
        self.assertTrue(SeedCheckpoint.objects.filter(key="research-publications-v1").exists())
        out = io.StringIO()
        call_command("seed_publications", stdout=out)
        self.assertIn("跳过", out.getvalue())
        self.assertFalse(Publication.objects.exists())
        self.assertEqual(Figure.objects.get().is_published, False)
