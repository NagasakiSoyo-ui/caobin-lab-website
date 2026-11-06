"""Apply the customer's reviewed authorship classification once, retaining source files."""
import hashlib
import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

from catalog.models import Publication, Resource, SeedCheckpoint
from catalog.pubmed import find_conflict


class Command(BaseCommand):
    help = '按已核验署名归类指南，恢复旧包学习资料；后续启动不覆盖后台修改。'

    @transaction.atomic
    def handle(self, *args, **options):
        data = json.loads((settings.BASE_DIR / 'seed/guideline-classification.json').read_text('utf8'))
        if SeedCheckpoint.objects.filter(key=data['checkpoint']).exists():
            self.stdout.write('指南归类已完成，保留后台后续修改。')
            return
        root = Path(settings.MEDIA_ROOT).resolve()
        created = 0
        for item in data['records']:
            resource = Resource.objects.select_for_update().filter(title=item['title'], document=item['document']).first()
            if not resource:
                raise CommandError(f"待归类原始资料缺失或已改名：{item['title']}")
            source = (root / item['document']).resolve()
            if not source.is_relative_to(root) or not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != item['sha256']:
                raise CommandError(f"原文文件缺失或已变更：{item['title']}")
            fields = item['publication']
            identified, conflict = find_conflict(fields.get('pmid'), fields.get('doi'))
            if conflict:
                raise CommandError(conflict)
            identity = Q(title=fields['title'])
            if identified:
                identity |= Q(pk=identified.pk)
            matches = list(Publication.objects.select_for_update().filter(identity))
            if len(matches) > 1:
                raise CommandError(f"成果匹配不唯一：{item['title']}")
            obj = matches[0] if matches else Publication(**fields)
            if matches:
                if ((obj.doi and fields.get('doi') and obj.doi != fields['doi'])
                        or (obj.pmid and fields.get('pmid') and obj.pmid != fields['pmid'])
                        or (obj.document and obj.document.name != item['document'])):
                    raise CommandError(f"已有成果标识或文件冲突：{item['title']}")
                # Classification is explicit; other existing editorial choices remain intact.
                obj.kind = fields['kind']
                obj.lab_role = fields['lab_role']
                for field in ('doi', 'pmid'):
                    if not getattr(obj, field):
                        setattr(obj, field, fields.get(field))
                obj.source_note = (obj.source_note + '\n' + fields['source_note']).strip()
                obj.version += 1
            else:
                created += 1
            obj.document = resource.document.name
            obj.full_clean()
            obj.save()
            resource.is_published = item['keep_learning']
            resource.version += 1
            resource.save(update_fields=['is_published', 'version', 'updated_at'])
        for item in data['restore_learning']:
            resource = Resource.objects.select_for_update().filter(title=item['title'], document=item['document']).first()
            if not resource:
                raise CommandError(f"旧包资料缺失或已改名：{item['title']}")
            resource.is_published = True
            resource.version += 1
            resource.save(update_fields=['is_published', 'version', 'updated_at'])
        detail = f'核验归类 {len(data["records"])} 份团队文献，新增成果 {created} 条；恢复旧包学习资料 {len(data["restore_learning"])} 份。'
        SeedCheckpoint.objects.create(key=data['checkpoint'], detail=detail)
        self.stdout.write(detail)
