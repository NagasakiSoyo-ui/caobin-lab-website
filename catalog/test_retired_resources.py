import io
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from .management.commands.remove_retired_resources import RETIRED_KINDS
from .models import Resource, Publication, SeedCheckpoint
from .test_research import MediaMixin


class RetiredResourcesTests(MediaMixin, TestCase):
    def resource(self, kind, published=False):
        return Resource.objects.create(title=kind, kind=kind, disease='测试',
                                       is_published=published, source_url=f'https://example.org/{kind}')

    def test_delete_only_retired_records_and_preserve_files(self):
        for kind in RETIRED_KINDS:
            self.resource(kind)
        keep = [self.resource('指南', True), self.resource('诊疗方案', True),
                self.resource('专家共识'), self.resource('指南解读')]
        before = list(Resource.objects.filter(pk__in=[obj.pk for obj in keep]).values())
        publications = list(Publication.objects.values())
        removed = Resource.objects.get(kind='研究文献')
        from django.conf import settings
        path = Path(settings.MEDIA_ROOT) / 'shared.pdf'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'shared existing file')
        Resource.objects.filter(pk=removed.pk).update(document='shared.pdf')
        call_command('remove_retired_resources', stdout=io.StringIO())
        self.assertEqual(list(Resource.objects.values()), before)
        self.assertEqual(list(Publication.objects.values()), publications)
        self.assertEqual(path.read_bytes(), b'shared existing file')
        self.assertFalse(Resource.objects.filter(kind__in=RETIRED_KINDS).exists())
        self.resource('研究文献')
        call_command('remove_retired_resources', stdout=io.StringIO())
        self.assertTrue(Resource.objects.filter(kind='研究文献').exists())

    def test_unexpected_public_content_aborts_without_partial_deletion(self):
        self.resource('书籍介绍')
        self.resource('病例讨论', True)
        with self.assertRaises(CommandError):
            call_command('remove_retired_resources', stdout=io.StringIO())
        self.assertEqual(Resource.objects.count(), 2)
        self.assertFalse(SeedCheckpoint.objects.exists())
