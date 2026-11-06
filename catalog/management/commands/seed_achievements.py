"""Import reviewed additions once, preserving subsequent customer edits and deletions."""
import json
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q
from catalog.models import Publication, SeedCheckpoint
from catalog.pubmed import find_conflict


class Command(BaseCommand):
    help = "一次性导入所选清单的成果并保留来源备注；后续运行不恢复客户删除的记录。"

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
            if obj.kind in ('patent', 'software') and (not obj.registration_number or not obj.registered_on):
                raise CommandError(f'缺少编号或日期：{obj.title}')
            identity = Q(kind=obj.kind, title=obj.title)
            if obj.slug:
                identity |= Q(slug=obj.slug)
            if obj.registration_number:
                identity |= Q(registration_number=obj.registration_number)
            identified, conflict = find_conflict(obj.pmid, obj.doi)
            if conflict:
                raise CommandError(conflict)
            if identified:
                identity |= Q(pk=identified.pk)
            matches = list(Publication.objects.select_for_update().filter(identity))
            if matches:
                if obj.kind == 'paper' and len(matches) == 1:
                    existing = matches[0]
                    if ((obj.doi and existing.doi and obj.doi != existing.doi)
                            or (obj.pmid and existing.pmid and obj.pmid != existing.pmid)):
                        raise CommandError(f'已有论文标识冲突：{obj.title}')
                    continue
                if len(matches) != 1 or any(getattr(matches[0], name) != getattr(obj, name) for name in item):
                    raise CommandError(f'已有记录与本次导入冲突，未覆盖：{obj.title}')
                continue
            obj.save()
            created += 1
        summary = f'新增 {created} 条成果。'
        SeedCheckpoint.objects.create(key=checkpoint, detail=summary)
        self.stdout.write(summary)
