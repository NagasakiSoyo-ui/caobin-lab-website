"""Apply an editorial resource order once, keeping dates, contents and visibility intact."""
import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from catalog.models import Resource, SeedCheckpoint


class Command(BaseCommand):
    help = '按审定清单前置代表性学习资料；其余公开资料同序号按年份排列，后续启动不覆盖编辑。'

    def add_arguments(self, parser):
        parser.add_argument('--file', default=str(settings.BASE_DIR / 'seed/resource-order.json'))

    @transaction.atomic
    def handle(self, *args, **options):
        data = json.loads(Path(options['file']).read_text('utf8'))
        if SeedCheckpoint.objects.filter(key=data['checkpoint']).exists():
            self.stdout.write('学习资料排序已设置，保留后台后续修改。')
            return
        selected = []
        for item in data['resources']:
            matches = list(Resource.objects.select_for_update().filter(**item, is_published=True))
            if len(matches) != 1 or matches[0].pk in selected:
                raise CommandError(f"排序资料缺失、未公开或匹配不唯一：{item['title']}")
            selected.append(matches[0].pk)
        default_position = Resource._meta.get_field('position').get_default()
        if not selected or len(selected) >= default_position:
            raise CommandError('排序清单需包含少于默认显示顺序数量的资料。')
        updates = {obj.pk: default_position for obj in Resource.objects.select_for_update().filter(is_published=True)}
        updates.update({pk: rank for rank, pk in enumerate(selected, 1)})
        now = timezone.now()
        for pk, position in updates.items():
            Resource.objects.filter(pk=pk).exclude(position=position).update(
                position=position, version=F('version') + 1, updated_at=now)
        summary = f'前置 {len(selected)} 份代表性资料，其余公开资料按年份排列。'
        SeedCheckpoint.objects.create(key=data['checkpoint'], detail=summary)
        self.stdout.write(summary)
