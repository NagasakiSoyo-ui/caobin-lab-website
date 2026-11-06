import io
import json
import tempfile
from datetime import date
from pathlib import Path
from zipfile import ZipFile

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from .exporting import website_archive
from .models import Publication, Resource, SeedCheckpoint
from .test_research import MediaMixin


@override_settings(ALLOWED_HOSTS=['testserver'])
class CatalogueLinksTests(MediaMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_site', stdout=io.StringIO())

    def batch(self, command, data):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'batch.json'
            path.write_text(json.dumps(data), 'utf8')
            call_command(command, file=str(path), stdout=io.StringIO())

    def test_link_validation_rejects_missing_target_unsafe_url_and_inconsistent_date(self):
        obj = Resource(title='Reference', kind='指南', disease='肺炎')
        with self.assertRaises(ValidationError):
            obj.full_clean()
        obj.source_url = 'javascript:alert(1)'
        with self.assertRaises(ValidationError):
            obj.full_clean()
        obj.source_url = 'https://example.org/article'
        obj.full_clean()  # An unknown date is valid and remains unknown.
        obj.published_on, obj.year = date(2026, 1, 1), 2025
        with self.assertRaises(ValidationError):
            obj.full_clean()

    def test_external_article_and_video_export_without_fake_download_or_zero_pages(self):
        for kind in ('研究进展', '视频课程'):
            Resource.objects.create(title=kind, kind=kind, disease='肺炎',
                                    source_url='https://example.org/' + ('article' if kind == '研究进展' else 'video'),
                                    is_published=True)
        with website_archive() as stream, ZipFile(stream) as archive:
            html = archive.read('resources.html').decode()
        self.assertIn('https://example.org/article', html)
        self.assertIn('https://example.org/video', html)
        self.assertIn('观看课程', html)
        self.assertNotIn('0 页', html)
        self.assertNotIn('0.0 MB', html)
        self.assertIn('resource-pagination', html)

    def test_new_resource_batch_preserves_existing_draft_and_restart_edits(self):
        obj = Resource.objects.create(title='Existing', kind='指南', disease='肺炎',
                                      source_url='https://example.org/existing', is_published=False)
        data = {'checkpoint': 'links-test', 'resources': [
            {'fields': {'title': title, 'kind': '指南', 'disease': '肺炎', 'source_url': url}}
            for title, url in [('Upstream title', obj.source_url), ('New', 'https://example.org/new')]]}
        self.batch('seed_resources', data)
        obj.refresh_from_db()
        self.assertEqual(obj.title, 'Existing')
        self.assertFalse(obj.is_published)
        Resource.objects.get(title='New').delete()
        self.batch('seed_resources', data)
        self.assertFalse(Resource.objects.filter(title='New').exists())

    def test_failed_resource_batch_changes_nothing(self):
        before = list(Resource.objects.values())
        data = {'checkpoint': 'invalid-links', 'resources': [
            {'fields': {'title': 'Good', 'kind': '指南', 'disease': '肺炎', 'source_url': 'https://example.org/a'}},
            {'fields': {'title': 'Bad', 'kind': '指南', 'disease': '肺炎'}}]}
        with self.assertRaises(ValidationError):
            self.batch('seed_resources', data)
        self.assertEqual(list(Resource.objects.values()), before)
        self.assertFalse(SeedCheckpoint.objects.filter(key='invalid-links').exists())

    def test_paper_identifiers_merge_without_blank_registration_collisions(self):
        original = Publication.objects.create(title='Customer edit', year=2025, doi='10.1000/one', is_published=False)
        data = {'checkpoint': 'papers-test', 'publications': [
            {'kind': 'paper', 'title': 'Original title', 'year': 2025, 'doi': '10.1000/one'},
            {'kind': 'paper', 'title': 'Different paper', 'year': 2026, 'doi': '10.1000/two'}]}
        self.batch('seed_achievements', data)
        original.refresh_from_db()
        self.assertFalse(original.is_published)
        self.assertEqual(original.title, 'Customer edit')
        self.assertEqual(Publication.objects.count(), 2)
        Publication.objects.get(doi='10.1000/two').delete()
        self.batch('seed_achievements', data)
        self.assertEqual(Publication.objects.count(), 1)

    def test_conflicting_paper_ids_roll_back_entire_batch(self):
        Publication.objects.create(title='One', year=2025, pmid='123', doi='10.1000/one')
        Publication.objects.create(title='Two', year=2025, pmid='456', doi='10.1000/two')
        data = {'checkpoint': 'conflicting-papers', 'publications': [
            {'kind': 'paper', 'title': 'New', 'year': 2026},
            {'kind': 'paper', 'title': 'Conflict', 'year': 2025, 'pmid': '123', 'doi': '10.1000/two'}]}
        with self.assertRaises(CommandError):
            self.batch('seed_achievements', data)
        self.assertEqual(Publication.objects.count(), 2)
        self.assertFalse(SeedCheckpoint.objects.filter(key='conflicting-papers').exists())

    def test_reviewed_full_catalogue_imports_and_repeats_without_changes(self):
        call_command('seed_publications', stdout=io.StringIO())
        original = list(Publication.objects.values())
        for command, filename in [('seed_achievements', 'chinapneumonia-publications.json'),
                                  ('seed_resources', 'chinapneumonia-resources.json')]:
            args = {'file': str(settings.BASE_DIR / 'seed' / filename), 'stdout': io.StringIO()}
            call_command(command, **args)
            snapshot = (list(Resource.objects.values()), list(Publication.objects.values()))
            call_command(command, **args)
            self.assertEqual((list(Resource.objects.values()), list(Publication.objects.values())), snapshot)
        self.assertEqual(list(Publication.objects.filter(pk__in=[r['id'] for r in original]).values()), original)
        self.assertGreater(Publication.objects.filter(kind='paper').count(), 300)
        self.assertEqual(Resource.objects.exclude(source_url='').count(), 886)
        self.assertEqual(Resource.objects.filter(kind='视频课程').count(), 149)
        self.assertFalse(Publication.objects.exclude(summary='').exclude(pk__in=[r['id'] for r in original]).exists())
