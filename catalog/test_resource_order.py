import io
import json
from pathlib import Path
import tempfile

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from .models import Resource, SeedCheckpoint


class ResourceOrderTests(TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.manifest = Path(self.temp.name) / 'order.json'
        self.older = Resource.objects.create(title='较早的代表性指南', year=2016, kind='指南', disease='肺炎',
                                            source_url='https://example.org/older', is_published=True)
        self.newer = Resource.objects.create(title='较新的资料', year=2026, kind='指南', disease='肺炎',
                                            source_url='https://example.org/newer', position=1, is_published=True)
        self.draft = Resource.objects.create(title='草稿', year=2026, kind='指南', disease='肺炎',
                                            source_url='https://example.org/draft', position=5)
        self.manifest.write_text(json.dumps({'checkpoint':'test-resource-order', 'resources':[
            {'title':self.older.title,'source_url':self.older.source_url,'document':''}]}), 'utf8')

    def order(self):
        call_command('order_resources', file=str(self.manifest), stdout=io.StringIO())

    def test_priority_precedes_year_without_changing_contents_or_drafts(self):
        before = {r['id']:r for r in Resource.objects.values()}
        self.order()
        self.assertEqual(list(Resource.objects.filter(is_published=True).values_list('pk',flat=True)),
                         [self.older.pk,self.newer.pk])
        for row in Resource.objects.values():
            for key in row:
                if key not in ('position','version','updated_at'):
                    self.assertEqual(row[key],before[row['id']][key])
        self.assertEqual(Resource.objects.values().get(pk=self.draft.pk),before[self.draft.pk])
        self.older.refresh_from_db()
        self.older.position = 50
        self.older.save()
        after = list(Resource.objects.values())
        self.order()
        self.assertEqual(list(Resource.objects.values()),after)

    def test_missing_selection_leaves_all_positions_unchanged(self):
        self.older.is_published = False
        self.older.save()
        before = list(Resource.objects.values())
        with self.assertRaisesMessage(CommandError,'排序资料缺失'):
            self.order()
        self.assertEqual(list(Resource.objects.values()),before)
        self.assertFalse(SeedCheckpoint.objects.exists())
