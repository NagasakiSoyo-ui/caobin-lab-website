import io
from pathlib import Path
from zipfile import ZipFile

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase, override_settings

from .exporting import website_archive
from .models import HomeSlide, ResearchDirection, SeedCheckpoint
from .test_research import MediaMixin


@override_settings(ALLOWED_HOSTS=['testserver'])
class HomeCarouselTests(MediaMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_site', stdout=io.StringIO())
        call_command('seed_publications', stdout=io.StringIO())

    def seed(self):
        call_command('seed_home_slides', stdout=io.StringIO())

    def test_slides_use_exact_existing_text_and_original_images(self):
        first = HomeSlide.objects.get()
        self.seed()
        self.assertEqual(HomeSlide.objects.count(), 4)
        first.refresh_from_db()
        for slide in HomeSlide.objects.exclude(pk=first.pk):
            source = ResearchDirection.objects.get(title=slide.title)
            self.assertEqual(slide.intro, source.text)
            self.assertEqual(slide.image_fit, 'contain')
            self.assertTrue(source.figures.filter(image=slide.photo.name).exists())
        html = self.client.get('/index.html').content.decode()
        self.assertEqual(html.count('data-slide role='), 4)
        self.assertEqual(html.count('hidden inert aria-hidden="true"'), 3)
        self.assertEqual(html.count('<h1>'), 1)
        self.assertIn('data-carousel-play hidden', html)

    def test_restart_preserves_customer_edits_and_deletions(self):
        self.seed()
        slide = HomeSlide.objects.last()
        slide.title = '客户编辑后的轮播'
        slide.is_published = False
        slide.save()
        HomeSlide.objects.exclude(pk=slide.pk).first().delete()
        before = list(HomeSlide.objects.values())
        self.seed()
        self.assertEqual(list(HomeSlide.objects.values()), before)

    def test_hidden_sources_are_not_republished(self):
        ResearchDirection.objects.filter(slug='viral-sepsis').update(is_published=False)
        self.seed()
        self.assertEqual(HomeSlide.objects.count(), 3)
        self.assertFalse(HomeSlide.objects.filter(title__contains='viral sepsis').exists())

    def test_zero_one_and_draft_slides(self):
        self.assertNotContains(self.client.get('/index.html'), 'data-carousel-controls')
        HomeSlide.objects.update(is_published=False)
        self.assertNotContains(self.client.get('/index.html'), 'data-carousel role=')
        self.assertContains(self.client.get('/index.html'), '全部研究方向')

    def test_offline_includes_every_slide_image_without_altering_bytes(self):
        self.seed()
        with website_archive() as stream, ZipFile(stream) as archive:
            for slide in HomeSlide.objects.all():
                self.assertEqual(archive.read('media/' + slide.photo.name),
                                 (Path(settings.MEDIA_ROOT) / slide.photo.name).read_bytes())
            self.assertIn('assets/home-carousel.js', archive.namelist())
            self.assertNotIn('/static/', archive.read('index.html').decode())

    def test_missing_image_rolls_back_partial_import(self):
        source = Path(settings.MEDIA_ROOT) / 'initial/figures/pmid39692191-fig1.jpg'
        original = source.read_bytes()
        source.unlink()
        try:
            with self.assertRaises(CommandError):
                self.seed()
            self.assertEqual(HomeSlide.objects.count(), 1)
            self.assertFalse(SeedCheckpoint.objects.filter(key='home-carousel-20261106').exists())
        finally:
            source.write_bytes(original)


class HomeCarouselMigrationTests(TransactionTestCase):
    def test_upgrade_preserves_edited_hero_exactly(self):
        executor = MigrationExecutor(connection)
        executor.migrate([('catalog', '0011_publication_document')])
        try:
            old = executor.loader.project_state([('catalog', '0011_publication_document')]).apps
            old.get_model('catalog', 'SiteSettings').objects.create(
                pk=1, name='团队名称', hero_title='客户原有标题', hero_english='Original title',
                hero_intro='客户原有介绍，原样保留。', hero_photo='uploads/customer.jpg')
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes('catalog'))
            slide = HomeSlide.objects.get()
            self.assertEqual((slide.title, slide.english, slide.intro, slide.photo.name, slide.is_published),
                             ('客户原有标题', 'Original title', '客户原有介绍，原样保留。', 'uploads/customer.jpg', True))
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes('catalog'))
