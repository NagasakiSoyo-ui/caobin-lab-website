"""Apply the customer's guideline-only publication selection once, without deleting records."""
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from catalog.models import Resource, SeedCheckpoint


class Command(BaseCommand):
    help = '学习资料仅保留已公开的指南与共识（含诊疗方案）；其他类型转为草稿，保留文件。'

    @transaction.atomic
    def handle(self, *args, **options):
        key = 'learning-guidelines-only-20261109'
        if SeedCheckpoint.objects.filter(key=key).exists():
            self.stdout.write('学习资料范围已调整，保留后台后续修改。')
            return
        # Use the same category definition as cards and filters; never republish drafts.
        records = list(Resource.objects.select_for_update().filter(is_published=True).only('id', 'kind'))
        retired = [obj.pk for obj in records if obj.category != '指南与共识']
        Resource.objects.filter(pk__in=retired).update(
            is_published=False, version=F('version') + 1, updated_at=timezone.now())
        summary = f'学习资料保留 {len(records) - len(retired)} 份指南与共识（含诊疗方案），其余 {len(retired)} 份转为草稿。'
        SeedCheckpoint.objects.create(key=key, detail=summary)
        self.stdout.write(summary)
