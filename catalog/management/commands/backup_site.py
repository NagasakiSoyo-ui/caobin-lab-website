import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile, ZIP_DEFLATED
from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "备份数据库及全部上传素材。备份含账号数据，仅应保存在私有位置。"

    def handle(self, *args, **options):
        folder = settings.DATA_DIR / "backups"
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / f"backup-{datetime.now():%Y%m%d-%H%M%S-%f}.zip"
        with TemporaryDirectory() as temp:
            copy = Path(temp) / "site.sqlite3"
            with closing(sqlite3.connect(settings.DATABASES["default"]["NAME"])) as source, closing(sqlite3.connect(copy)) as dest:
                source.backup(dest)
            with ZipFile(target, "x", ZIP_DEFLATED) as archive:
                archive.write(copy, "site.sqlite3")
                for file in Path(settings.MEDIA_ROOT).rglob("*"):
                    if file.is_file():
                        archive.write(file, "media/" + file.relative_to(settings.MEDIA_ROOT).as_posix())
        self.stdout.write(str(target))
