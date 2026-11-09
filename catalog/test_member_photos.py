import hashlib
import io
import json
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.template.loader import render_to_string
from django.test import TestCase

from .models import Member, SeedCheckpoint
from .test_research import MediaMixin


class MemberPhotoImportTests(MediaMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_site', stdout=io.StringIO())

    def seed(self):
        call_command('seed_member_photos', stdout=io.StringIO())

    def test_original_photos_match_names_and_groups(self):
        before = list(Member.objects.exclude(group='faculty').values())
        count = Member.objects.count()
        self.seed()
        self.assertEqual(Member.objects.count(), count + 6)
        manifest = json.loads((settings.BASE_DIR / 'seed/member-photos.json').read_text('utf8'))
        self.assertEqual(len(manifest['members']), 14)
        for item in manifest['members']:
            member = Member.objects.get(name=item['name'], group=item['group'])
            self.assertEqual(hashlib.sha256(Path(member.photo.path).read_bytes()).hexdigest(), item['photo']['sha256'])
            self.assertEqual(member.workplace, '')
        for row in before:
            self.assertEqual(Member.objects.values().get(pk=row['id']), row)

    def test_restart_preserves_removal_and_customer_edits(self):
        self.seed()
        member = Member.objects.get(name='王一民', group='faculty')
        member.photo = ''
        member.is_published = False
        member.save()
        Member.objects.get(name='何迪', group='postdocs').delete()
        before = list(Member.objects.values())
        self.seed()
        self.assertEqual(list(Member.objects.values()), before)

    def test_conflict_does_not_partially_import(self):
        member = Member.objects.get(name='王一民', group='faculty')
        member.photo = 'uploads/customer-photo.jpg'
        member.save()
        before = list(Member.objects.values())
        with self.assertRaisesMessage(CommandError, '成员已有不同照片'):
            self.seed()
        self.assertEqual(list(Member.objects.values()), before)
        self.assertFalse(SeedCheckpoint.objects.filter(key='team-photos-20261109').exists())
        self.assertFalse((Path(settings.MEDIA_ROOT) / 'initial/assets/people/faculty-周飞.png').exists())

    def test_faculty_and_postdoc_cards_show_only_name(self):
        for group in ('faculty', 'postdocs', 'students', 'alumni'):
            member = Member(name='测试姓名', group=group, school='学校信息', workplace='单位信息',
                            stage='阶段信息', cohort='年级信息', bio='介绍信息')
            rendered = render_to_string('public/member.html', {'member': member})
            self.assertIn('测试姓名', rendered)
            for value in ('学校信息', '单位信息', '阶段信息', '年级信息', '介绍信息'):
                if group in ('faculty', 'postdocs'):
                    self.assertNotIn(value, rendered)
                else:
                    self.assertIn(value, rendered)
