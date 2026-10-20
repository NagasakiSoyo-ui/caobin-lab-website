from pathlib import Path
import shutil
from django.conf import settings
from django.core.management.base import BaseCommand
from catalog.exporting import website_archive


class Command(BaseCommand):
    help = "导出数据库中当前公开的内容为完整离线 ZIP。"

    def add_arguments(self, parser):
        parser.add_argument("--output", default=str(settings.BASE_DIR / "exports/caobin-lab-offline.zip"))

    def handle(self, *args, **options):
        output = Path(options["output"]).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        with website_archive() as stream, output.open("wb") as file:
            shutil.copyfileobj(stream, file)
        self.stdout.write(self.style.SUCCESS(str(output)))
