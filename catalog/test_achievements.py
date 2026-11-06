import io
import json
from datetime import date
from zipfile import ZipFile
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from .exporting import website_archive
from .models import Publication, SeedCheckpoint
from .test_research import MediaMixin


@override_settings(ALLOWED_HOSTS=['testserver'])
class AchievementImportTests(MediaMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_site', stdout=io.StringIO())
        call_command('seed_publications', stdout=io.StringIO())

    def import_data(self):
        call_command('seed_achievements', stdout=io.StringIO())

    def test_verified_patents_match_source_and_export_without_unverified_software(self):
        original = list(Publication.objects.values())
        self.import_data()
        self.assertEqual(list(Publication.objects.filter(kind='paper').values()), original)
        self.assertEqual(Publication.objects.filter(kind='patent').count(), 6)
        self.assertFalse(Publication.objects.filter(kind='software').exists())
        data = json.loads((settings.BASE_DIR / 'seed/achievements.json').read_text('utf8'))
        html = self.client.get('/publications.html').content.decode()
        with website_archive() as stream, ZipFile(stream) as archive:
            offline = archive.read('publications.html').decode()
        for item in data['publications']:
            obj = Publication.objects.get(slug=item['slug'])
            self.assertEqual(obj.registered_on.isoformat(), item['registered_on'])
            for field in ('title', 'authors', 'registration_number'):
                self.assertEqual(getattr(obj, field), item[field])
                self.assertIn(item[field], html)
                self.assertIn(item[field], offline)
            self.assertFalse(obj.summary)
            self.assertFalse(obj.directions.exists())
            self.assertFalse(obj.figures.exists())
        for number in ('2025SR0462060', '2025SR0462049'):
            self.assertNotIn(number, html)
            self.assertNotIn(number, offline)
        self.assertIn('专利原文', html)
        self.assertIn('2025-03-04', html)

    def test_repeated_start_keeps_customer_edits_and_deletions(self):
        self.import_data()
        obj = Publication.objects.get(slug='patent-cn113156113b')
        obj.title = '客户已修改的名称'
        obj.is_published = False
        obj.save()
        Publication.objects.get(slug='patent-cn119351536b').delete()
        self.import_data()
        obj.refresh_from_db()
        self.assertEqual(obj.title, '客户已修改的名称')
        self.assertFalse(obj.is_published)
        self.assertEqual(Publication.objects.filter(kind='patent').count(), 5)

    def test_patents_are_separate_from_paper_year_filters(self):
        self.import_data()
        response = self.client.get('/publications.html')
        self.assertEqual(len(response.context['papers']), 11)
        groups = response.context['achievement_sections']
        self.assertEqual([(group['kind'], len(group['items'])) for group in groups], [('patent', 6)])
        self.assertNotIn(2023, response.context['publication_years'])
        self.assertContains(response, 'href="#achievements-patent"')
        html = response.content.decode()
        before, patents = html.split('<section class="section" id="achievements-patent">')
        self.assertNotIn('ZL 2021 1 0111066.8', before)
        self.assertIn('ZL 2021 1 0111066.8', patents)

    def test_patent_only_page_and_empty_categories(self):
        self.import_data()
        Publication.objects.filter(kind='paper').update(is_published=False)
        response = self.client.get('/publications.html')
        self.assertNotContains(response, 'data-publication-year')
        self.assertContains(response, '国家发明专利')
        self.assertNotContains(response, '软件著作权')
        self.assertNotContains(response, '成果目录整理中')

    def test_conflict_rolls_back_the_whole_batch(self):
        Publication.objects.create(kind='patent', title='已有人工记录', year=2025,
                                   registration_number='ZL 2024 1 1313198.9')
        with self.assertRaises(CommandError):
            self.import_data()
        self.assertEqual(Publication.objects.filter(kind='patent').count(), 1)
        self.assertFalse(SeedCheckpoint.objects.filter(key='verified-patents-20261106').exists())

    def test_registration_year_must_match_date(self):
        obj = Publication(kind='patent', title='测试', year=2023, registered_on=date(2025, 3, 4))
        with self.assertRaises(ValidationError) as error:
            obj.full_clean()
        self.assertIn('year', error.exception.message_dict)

    def test_software_has_its_own_section_and_preserves_supplied_metadata(self):
        self.import_data()
        call_command('seed_achievements', file=str(settings.BASE_DIR / 'seed/software.json'), stdout=io.StringIO())
        response = self.client.get('/publications.html')
        self.assertEqual([(s['kind'], len(s['items'])) for s in response.context['achievement_sections']],
                         [('patent', 6), ('software', 2)])
        self.assertContains(response, 'href="#achievements-software"')
        with website_archive() as stream, ZipFile(stream) as archive:
            htmls = [response.content.decode(), archive.read('publications.html').decode()]
        data = json.loads((settings.BASE_DIR / 'seed/software.json').read_text('utf8'))
        for html in htmls:
            before, software = html.split('<section class="section" id="achievements-software">')
            for item in data['publications']:
                self.assertNotIn(item['registration_number'], before)
                for field in ('title', 'authors', 'registration_number', 'registered_on'):
                    self.assertIn(item[field], software)
            self.assertNotIn('来源链接', software)
            self.assertNotIn('尚未完成公开核验', software)
        for obj in Publication.objects.filter(kind='software'):
            self.assertEqual(obj.source_note, '')
            self.assertFalse(obj.url)
            self.assertFalse(obj.summary)

    def test_software_initialization_preserves_later_edits_and_deletions(self):
        options = {'file': str(settings.BASE_DIR / 'seed/software.json'), 'stdout': io.StringIO()}
        call_command('seed_achievements', **options)
        obj = Publication.objects.get(registration_number='2025SR0462060')
        obj.title = '客户更新名称'
        obj.is_published = False
        obj.save()
        Publication.objects.get(registration_number='2025SR0462049').delete()
        call_command('seed_achievements', **options)
        obj.refresh_from_db()
        self.assertEqual(obj.title, '客户更新名称')
        self.assertFalse(obj.is_published)
        self.assertEqual(Publication.objects.filter(kind='software').count(), 1)
