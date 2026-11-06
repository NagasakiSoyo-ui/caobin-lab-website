import hashlib
import io
import json
from pathlib import Path
from zipfile import ZipFile

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from .exporting import website_archive
from .models import Publication, Resource, SeedCheckpoint
from .test_research import MediaMixin


@override_settings(ALLOWED_HOSTS=['testserver'])
class GuidelineClassificationTests(MediaMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        for command in ('seed_site', 'seed_resources', 'seed_publications'):
            call_command(command, stdout=io.StringIO())
        call_command('seed_achievements', file=str(settings.BASE_DIR / 'seed/chinapneumonia-publications.json'), stdout=io.StringIO())

    def classify(self):
        call_command('classify_guidelines', stdout=io.StringIO())

    def test_authorship_routes_guides_and_papers_without_duplicating_existing_outputs(self):
        before = Publication.objects.count()
        self.classify()
        self.assertEqual(Publication.objects.count(), before + 10)
        self.assertEqual(Publication.objects.filter(kind='guideline').count(), 10)
        self.assertEqual(Publication.objects.filter(kind='paper').count(), 305)
        self.assertEqual(Publication.objects.exclude(document='').count(), 12)
        self.assertEqual(Publication.objects.filter(doi='10.1183/13993003.02611-2025').count(), 1)
        self.assertEqual(Publication.objects.get(doi='10.1164/rccm.202507-1692st').lab_role, 'participant')
        self.assertFalse(Publication.objects.filter(title='流行性感冒诊疗方案（2020年版）').exists())
        self.assertEqual(Resource.objects.filter(is_published=True).count(), 10)
        self.assertTrue(Resource.objects.get(title='中国流感治疗与药物预防临床实践指南（2025版）').is_published)
        data = json.loads((settings.BASE_DIR / 'seed/guideline-classification.json').read_text('utf8'))
        for item in data['restore_learning']:
            self.assertTrue(Resource.objects.get(document=item['document']).is_published)
            self.assertFalse(Publication.objects.filter(title=item['title']).exists())

    def test_repeat_preserves_admin_edits_deletes_and_visibility(self):
        self.classify()
        obj = Publication.objects.filter(kind='guideline').first()
        obj.title = '客户修改后的指南标题'
        obj.is_published = False
        obj.save()
        Publication.objects.filter(kind='guideline').exclude(pk=obj.pk).first().delete()
        Resource.objects.filter(is_published=True).update(is_published=False)
        before = (list(Publication.objects.values()), list(Resource.objects.values()))
        self.classify()
        self.assertEqual((list(Publication.objects.values()), list(Resource.objects.values())), before)

    def test_missing_source_rolls_back_entire_classification(self):
        resource = Resource.objects.get(title='中国成人2019冠状病毒病的诊治与防控指南')
        resource.title = '客户已改名，需要重新核对'
        resource.save()
        before = (list(Publication.objects.values()), list(Resource.objects.values()))
        with self.assertRaises(CommandError):
            self.classify()
        self.assertEqual((list(Publication.objects.values()), list(Resource.objects.values())), before)
        self.assertFalse(SeedCheckpoint.objects.filter(key='guideline-authorship-classification-20261106').exists())

    def test_original_pdf_bytes_survive_routing_and_offline_export(self):
        self.classify()
        data = json.loads((settings.BASE_DIR / 'seed/guideline-classification.json').read_text('utf8'))
        response = self.client.get('/publications.html')
        self.assertContains(response, 'id="achievements-guideline"')
        self.assertContains(response, '阅读原文 · PDF')
        with website_archive() as stream, ZipFile(stream) as archive:
            hashes = {hashlib.sha256(archive.read(name)).hexdigest() for name in archive.namelist() if name.endswith('.pdf')}
            self.assertIn('achievements-guideline', archive.read('publications.html').decode())
            for item in data['records']:
                self.assertIn(item['sha256'], hashes)
                obj = Publication.objects.get(doi=item['publication']['doi'])
                self.assertTrue(obj.original_url.startswith('/media/'))

    def test_overview_groups_types_and_caps_each_preview_without_losing_catalogue(self):
        self.classify()
        for index in range(8):
            Resource.objects.create(title=f'病例 {index}', kind='病例讨论', disease='肺炎',
                                    source_url=f'https://example.org/{index}', year=2026, is_published=True)
        response = self.client.get('/resources.html')
        groups = {group['kind']: group for group in response.context['resource_groups']}
        self.assertEqual(groups['病例讨论']['count'], 8)
        self.assertEqual(len(groups['病例讨论']['preview']), 3)
        self.assertIn('指南与共识', groups)
        self.assertNotIn('专家共识', groups)
        self.assertEqual(len(response.context['resources']), 18)
        self.assertContains(response, 'resource-overview')
        self.assertContains(response, '返回分类概览')
