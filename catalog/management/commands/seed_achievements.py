"""Import reviewed additions once, preserving subsequent customer edits and deletions."""
import json
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q
from catalog.models import Publication, SeedCheckpoint


class Command(BaseCommand):
    help = "一次性导入经核实的专利等成果；待核实项目不会导入，后续运行不恢复客户删除的记录。"

    def add_arguments(self, parser):
        parser.add_argument('--file', default=str(settings.BASE_DIR / 'seed/achievements.json'))

    @transaction.atomic
    def handle(self, *args, **options):
        data = json.loads(Path(options['file']).read_text('utf8'))
        checkpoint = data['checkpoint']
        if SeedCheckpoint.objects.filter(key=checkpoint).exists():
            self.stdout.write('补充成果已导入，跳过；保留现有编辑和删除。')
            return
        created = 0
        for item in data['publications']:
            obj = Publication(**item)
            obj.full_clean(validate_unique=False)
            if not obj.registration_number or not obj.registered_on or not obj.url or not obj.source_note:
                raise CommandError(f'缺少编号、日期或核验来源：{obj.title}')
            matches = list(Publication.objects.filter(
                Q(slug=obj.slug) | Q(registration_number=obj.registration_number) | Q(kind=obj.kind, title=obj.title)))
            if matches:
                if len(matches) != 1 or any(getattr(matches[0], name) != getattr(obj, name) for name in item):
                    raise CommandError(f'已有记录与本次导入冲突，未覆盖：{obj.title}')
                continue
            obj.save()
            created += 1
        summary = f'新增 {created} 条已核实成果。'
        SeedCheckpoint.objects.create(key=checkpoint, detail=summary)
        self.stdout.write(summary)
