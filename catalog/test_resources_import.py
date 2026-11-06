import io
import json
from pathlib import Path
from zipfile import ZipFile

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from .exporting import website_archive
from .models import Resource, SeedCheckpoint
from .test_research import MediaMixin


@override_settings(ALLOWED_HOSTS=['testserver'])
class ResourceImportTests(MediaMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_site', stdout=io.StringIO())

    def import_data(self):
        call_command('seed_resources', stdout=io.StringIO())

    def test_merge_and_retirement_preserve_other_resources_and_export(self):
        old = list(Resource.objects.filter(document__in=[
            'initial/documents/resource-02.pdf', 'initial/documents/resource-06.pdf',
            'initial/documents/resource-09.pdf']).values())
        self.import_data()
        self.assertEqual(list(Resource.objects.filter(pk__in=[r['id'] for r in old]).values()), old)
        self.assertEqual(Resource.objects.count(), 21)
        self.assertEqual(Resource.objects.filter(is_published=True).count(), 16)
        self.assertEqual(Resource.objects.filter(is_published=False).count(), 5)
        self.assertEqual(Resource.objects.filter(title='中国流感治疗与药物预防临床实践指南（2025版）').count(), 1)
        self.assertEqual(Resource.objects.filter(title__contains='宏基因组二代测序报告').count(), 1)
        response = self.client.get('/resources.html')
        self.assertContains(response, '共 16 份资料')
        for disease in ('慢阻肺', '哮喘', '支气管扩张'):
            self.assertNotContains(response, disease)
        with website_archive() as stream, ZipFile(stream) as archive:
            html = archive.read('resources.html').decode()
            self.assertIn('共 16 份资料', html)
            for resource in Resource.objects.filter(is_published=True):
                self.assertIn(resource.title, html)
            for resource in Resource.objects.filter(is_published=False):
                self.assertNotIn(resource.title, html)
            for item in json.loads((settings.BASE_DIR / 'seed/learning-resources.json').read_text('utf8'))['resources']:
                expected = (settings.BASE_DIR / 'seed' / item['document']['path']).read_bytes()
                obj = Resource.objects.get(title=item['fields']['title'])
                with obj.document.open('rb') as document:
                    self.assertEqual(document.read(), expected)
                self.assertTrue(any(archive.read(name) == expected for name in archive.namelist() if name.endswith(obj.download_name)))

    def test_repeat_preserves_customer_edits_deletions_and_publication_choices(self):
        self.import_data()
        obj = Resource.objects.get(title__startswith='靶向高通量')
        obj.title = '客户修改的标题'
        obj.is_published = False
        obj.save()
        Resource.objects.get(title__startswith='Clinical practice guideline').delete()
        old = Resource.objects.filter(is_published=False, disease='慢阻肺').first()
        old.is_published = True
        old.save()
        before = list(Resource.objects.values())
        self.import_data()
        self.assertEqual(list(Resource.objects.values()), before)

    def test_conflicting_title_rolls_back_batch(self):
        Resource.objects.create(title='靶向高通量测序在感染性疾病中应用与实践专家共识',
                                document='uploads/customer.pdf', pages=1, file_bytes=10, year=2024,
                                kind='专家共识', disease='病原学诊断')
        before = list(Resource.objects.values())
        with self.assertRaisesMessage(CommandError, '冲突'):
            self.import_data()
        self.assertEqual(list(Resource.objects.values()), before)
        self.assertFalse(SeedCheckpoint.objects.filter(key='guidelines-resources-20261106').exists())

    def test_modified_target_is_not_overwritten(self):
        item = json.loads((settings.BASE_DIR / 'seed/learning-resources.json').read_text('utf8'))['resources'][0]
        target = Path(settings.MEDIA_ROOT) / 'initial' / item['document']['path']
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b'customer file')
        self.addCleanup(target.unlink)
        before = list(Resource.objects.values())
        with self.assertRaisesMessage(CommandError, '目标素材已被修改'):
            self.import_data()
        self.assertEqual(target.read_bytes(), b'customer file')
        self.assertEqual(list(Resource.objects.values()), before)
