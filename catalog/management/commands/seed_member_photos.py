"""Admit a reviewed member-photo batch once without replacing customer edits."""
import hashlib
import json
from pathlib import Path
import shutil

from django.conf import settings
from django.core.files import File
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Max

from catalog.models import Member, SeedCheckpoint
from catalog.validators import validate_image


class Command(BaseCommand):
    help = "一次性按姓名和分组导入成员原始照片；后续启动保留客户修改和删除。"

    def add_arguments(self, parser):
        parser.add_argument('--file', default=str(settings.BASE_DIR / 'seed/member-photos.json'))

    @transaction.atomic
    def handle(self, *args, **options):
        data = json.loads(Path(options['file']).read_text('utf8'))
        if SeedCheckpoint.objects.filter(key=data['checkpoint']).exists():
            self.stdout.write('成员照片已导入，保留现有编辑和删除。')
            return
        source_root = (settings.BASE_DIR / 'seed').resolve()
        media_root = Path(settings.MEDIA_ROOT).resolve()
        updates, assets, identities = [], {}, set()
        next_position = {group: (Member.objects.filter(group=group).aggregate(n=Max('position'))['n'] or 0) + 1
                         for group, _ in Member.GROUPS}
        for item in data['members']:
            name, group = item['name'], item['group']
            identity = (group, name)
            if group not in next_position or not name.strip() or name != name.strip() or identity in identities:
                raise CommandError(f'成员姓名或分组无效、重复：{name}')
            identities.add(identity)
            spec = item['photo']
            source = (source_root / spec['path']).resolve()
            relative = f"initial/{spec['path']}"
            target = (media_root / relative).resolve()
            if not source.is_relative_to(source_root) or not target.is_relative_to(media_root):
                raise CommandError(f'照片路径超出素材目录：{name}')
            if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != spec['sha256']:
                raise CommandError(f'照片缺失或校验失败：{name}')
            with source.open('rb') as stream:
                validate_image(File(stream, name=source.name))
            if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() != spec['sha256']:
                raise CommandError(f'已有照片文件被修改，未覆盖：{name}')
            matches = list(Member.objects.select_for_update().filter(name=name, group=group))
            if len(matches) > 1:
                raise CommandError(f'同组姓名匹配不唯一：{name}')
            if matches:
                obj = matches[0]
                if obj.photo.name and obj.photo.name != relative:
                    raise CommandError(f'成员已有不同照片，未覆盖：{name}')
                obj.version += 1
            else:
                obj = Member(name=name, group=group, position=next_position[group], is_published=True)
                next_position[group] += 1
            obj.photo = relative
            obj.full_clean()
            updates.append(obj)
            assets[target] = source
        # Check the whole batch before saving rows or copying files. If interrupted,
        # identical copied assets are safe to reuse; differing files are never replaced.
        for target, source in assets.items():
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
        created = sum(obj.pk is None for obj in updates)
        for obj in updates:
            obj.save()
        summary = f'导入 {len(updates)} 张原始照片，新增 {created} 位成员。'
        SeedCheckpoint.objects.create(key=data['checkpoint'], detail=summary)
        self.stdout.write(summary)
