"""Apply a reviewed learning-resource batch once, preserving subsequent admin edits."""
import hashlib
import json
import shutil
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

from catalog.models import Resource, SeedCheckpoint


class Command(BaseCommand):
    help = "一次性导入学习资料清单；同版合并、指定旧资料下架，此后启动保留后台修改。"

    def add_arguments(self, parser):
        parser.add_argument('--file', default=str(settings.BASE_DIR / 'seed/learning-resources.json'))

    @transaction.atomic
    def handle(self, *args, **options):
        manifest = Path(options['file'])
        data = json.loads(manifest.read_text('utf8'))
        if SeedCheckpoint.objects.filter(key=data['checkpoint']).exists():
            self.stdout.write('学习资料批次已导入，跳过；保留后台编辑、下架和删除。')
            return
        source_root = manifest.parent.resolve()
        media_root = Path(settings.MEDIA_ROOT).resolve()
        assets, updates, retirements = {}, [], []
        titles = set()
        for item in data['resources']:
            fields = item['fields'].copy()
            if fields['title'] in titles:
                raise CommandError(f"清单中标题重复：{fields['title']}")
            titles.add(fields['title'])
            for field in ('document', 'cover'):
                spec = item[field]
                source = (source_root / spec['path']).resolve()
                name = 'initial/' + spec['path']
                target = (media_root / name).resolve()
                if not source.is_relative_to(source_root) or not target.is_relative_to(media_root):
                    raise CommandError(f"素材路径越界：{spec['path']}")
                if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != spec['sha256']:
                    raise CommandError(f"素材缺失或校验失败：{spec['path']}")
                if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() != spec['sha256']:
                    raise CommandError(f"目标素材已被修改，未覆盖：{name}")
                assets[target] = source
                fields[field] = name
            # PDFs were reviewed before admission; keep the original bytes, including
            # reader-compatible permission encryption. No PDF rewriting at startup.
            if source_root.joinpath(item['document']['path']).stat().st_size != fields['file_bytes'] or fields['pages'] < 1:
                raise CommandError(f"PDF 元数据与清单不符：{fields['title']}")
            match = Q(title=fields['title']) | Q(document=fields['document'])
            previous = item.get('previous_document')
            if previous:
                match |= Q(document=previous)
            existing = list(Resource.objects.select_for_update().filter(match))
            if len(existing) > 1:
                raise CommandError(f"已有资料匹配不唯一：{fields['title']}")
            obj = existing[0] if existing else Resource()
            if obj.pk and (obj.title != fields['title'] or obj.document.name not in (previous, fields['document'])):
                raise CommandError(f"已有资料与清单冲突，未覆盖：{fields['title']}")
            if obj.pk:
                obj.version += 1
            for field, value in fields.items():
                setattr(obj, field, value)
            obj.full_clean()
            updates.append(obj)
        for item in data['retire']:
            existing = list(Resource.objects.select_for_update().filter(
                Q(title=item['title']) | Q(document=item['document'])))
            for obj in existing:
                if obj.title != item['title'] or obj.document.name != item['document']:
                    raise CommandError(f"待下架资料已被修改，请核对：{item['title']}")
                retirements.append(obj)
        # Validate the entire batch before copying files or changing any rows.
        # Identical staged assets can be reused after an interrupted transaction.
        for target, source in assets.items():
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
        created = sum(obj.pk is None for obj in updates)
        for obj in updates:
            obj.save()
        for obj in retirements:
            obj.is_published = False
            obj.version += 1
            obj.save(update_fields=['is_published', 'version', 'updated_at'])
        summary = f'新增 {created} 份，更新 {len(updates) - created} 份，下架 {len(retirements)} 份学习资料。'
        SeedCheckpoint.objects.create(key=data['checkpoint'], detail=summary)
        self.stdout.write(summary)
