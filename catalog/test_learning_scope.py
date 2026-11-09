import hashlib
import io
import json
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase, override_settings

from .models import Member, Publication, Resource
from .presentation import website_context
from .test_research import MediaMixin


@override_settings(ALLOWED_HOSTS=['testserver'])
class LearningScopeTests(MediaMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_site', stdout=io.StringIO())

    def test_only_guidelines_and_plans_remain_without_deleting_content(self):
        for kind in ('指南与共识', '诊疗方案', '书籍介绍', '学习心得', '病例讨论',
                     '研究文献', '研究进展', '学术活动', '科普文章', '视频课程'):
            Resource.objects.create(title=f'范围测试-{kind}', kind=kind, disease='测试方向',
                                    source_url=f'https://example.org/{Resource.objects.count()}', is_published=True)
        draft = Resource.objects.create(title='保留草稿', kind='专家共识', disease='测试方向',
                                        source_url='https://example.org/draft', is_published=False)
        before = {r.pk: r for r in Resource.objects.all()}
        publications = list(Publication.objects.values())
        call_command('curate_learning_resources', stdout=io.StringIO())
        self.assertEqual(Resource.objects.count(), len(before))
        for obj in Resource.objects.all():
            old = before[obj.pk]
            self.assertEqual(obj.title, old.title)
            self.assertEqual(obj.kind, old.kind)
            self.assertEqual(obj.document.name, old.document.name)
            self.assertEqual(obj.source_url, old.source_url)
            self.assertEqual(obj.is_published, old.is_published and old.category == '指南与共识')
        draft.refresh_from_db()
        self.assertFalse(draft.is_published)
        self.assertEqual(list(Publication.objects.values()), publications)
        self.assertEqual({r.category for r in website_context('resources')['resources']}, {'指南与共识'})
        html = self.client.get('/resources.html').content.decode()
        self.assertIn('范围测试-诊疗方案', html)
        self.assertNotIn('data-resource-category="诊疗方案"', html)
        self.assertNotIn('范围测试-视频课程', html)

    def test_repeat_does_not_restore_deleted_or_override_edited_records(self):
        call_command('curate_learning_resources', stdout=io.StringIO())
        obj = Resource.objects.first()
        obj.is_published = False
        obj.save()
        Resource.objects.exclude(pk=obj.pk).first().delete()
        before = list(Resource.objects.values())
        call_command('curate_learning_resources', stdout=io.StringIO())
        self.assertEqual(list(Resource.objects.values()), before)

    def test_missing_member_photo_uses_original_and_preserves_profile(self):
        member = Member.objects.get(name='刘东', group='students')
        before = Member.objects.values().get(pk=member.pk)
        source = settings.BASE_DIR / 'seed/member-photo-liudong.json'
        call_command('seed_member_photos', file=str(source), stdout=io.StringIO())
        after = Member.objects.values().get(pk=member.pk)
        for field in before:
            if field not in ('photo', 'version', 'updated_at'):
                self.assertEqual(before[field], after[field])
        item = json.loads(source.read_text('utf8'))['members'][0]
        member.refresh_from_db()
        self.assertEqual(hashlib.sha256(Path(member.photo.path).read_bytes()).hexdigest(), item['photo']['sha256'])
        member.photo = ''
        member.save()
        call_command('seed_member_photos', file=str(source), stdout=io.StringIO())
        member.refresh_from_db()
        self.assertFalse(member.photo)
