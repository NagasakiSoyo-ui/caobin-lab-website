import json
import shutil
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from catalog.models import Figure, Project, Publication, ResearchDirection, SeedCheckpoint
from catalog.pubmed import find_conflict

FILLABLE = ("pmcid", "summary", "source_note", "citation", "journal", "authors")
CHECKPOINT = "research-publications-v1"


class Command(BaseCommand):
    help = ("一次性导入 seed/research-publications.json 中已核验的首批成果、配图与方向关联。"
            "成功后在数据库记录初始化完成，此后再运行（包括每次启动）不会改动任何内容，"
            "后台删除或清空的内容不会被恢复。导入失败整体回滚、不记录完成，可重新运行。")

    def add_arguments(self, parser):
        parser.add_argument("--file", default=str(settings.BASE_DIR / "seed/research-publications.json"))
        parser.add_argument("--refill", action="store_true",
                            help="维护用：忽略完成记录再执行一次补充（只新增缺少的成果和配图、只填空白字段，"
                                 "会恢复此前删除的首批内容）。正常使用不需要。")

    @transaction.atomic
    def handle(self, *args, **options):
        done = SeedCheckpoint.objects.select_for_update().filter(key=CHECKPOINT).first()
        if done and not options["refill"]:
            self.stdout.write(f"首批成果已于 {timezone.localtime(done.completed_at):%Y-%m-%d %H:%M} 完成初始化，跳过；不改动现有内容。")
            return
        source = Path(options["file"])
        data = json.loads(source.read_text(encoding="utf-8"))
        directions = {d.slug: d for d in ResearchDirection.objects.all()}
        stats = {"created": 0, "filled": 0, "figures": 0, "conflicts": []}

        def pick(slugs):
            return [directions[s] for s in slugs if s in directions]

        for item in data["publications"]:
            match, conflict = find_conflict(item["pmid"], item["doi"])
            if conflict:
                stats["conflicts"].append(conflict)
                continue
            publication = match
            if publication is None:
                slug = item["slug"] if not Publication.objects.filter(slug=item["slug"]).exists() else None
                publication = Publication.objects.create(
                    kind="paper", title=item["title"], authors=item["authors"], year=item["year"],
                    journal=item["journal"], citation=item["citation"], pmid=item["pmid"], doi=item["doi"],
                    pmcid=item["pmcid"], url=f"https://pubmed.ncbi.nlm.nih.gov/{item['pmid']}/",
                    summary=item["summary"], slug=slug, lab_role=item["lab_role"],
                    source_note=item["source_note"], is_published=True)
                publication.directions.set(pick(item["directions"]))
                stats["created"] += 1
            else:
                changed = [f for f in FILLABLE if not getattr(publication, f) and item.get(f)]
                for field in changed:
                    setattr(publication, field, item[field])
                for field in ("pmid", "doi"):
                    if not getattr(publication, field):
                        setattr(publication, field, item[field])
                        changed.append(field)
                if changed:
                    publication.version += 1
                    publication.save()
                    stats["filled"] += 1
                if not publication.directions.exists():
                    publication.directions.set(pick(item["directions"]))
            # Figures are added only while a publication has none, so figures an editor removed
            # or replaced are not brought back on the next run.
            if item["figures"] and not publication.figures.exists():
                for spec in item["figures"]:
                    figure = Figure(kind="original", publication=publication, label=spec["label"], title=spec["title"],
                                    caption=spec["caption"], alt=spec["alt"], credit=spec["credit"],
                                    source_url=spec["source_url"], license_note=spec["license_note"],
                                    position=spec["position"], is_published=True)
                    figure.image.name = self.copy_asset(spec["file"])
                    figure.save()
                    figure.directions.set(pick(spec["directions"]))
                    stats["figures"] += 1

        for code, slugs in data.get("project_directions", {}).items():
            for project in Project.objects.filter(code=code):
                if not project.directions.exists():
                    project.directions.set(pick(slugs))

        summary = (f"成果新增 {stats['created']} 条，补全空白字段 {stats['filled']} 条，"
                   f"新增配图 {stats['figures']} 张，冲突 {len(stats['conflicts'])} 条。")
        # Same transaction as the import: a failure above rolls back both, so the run can be retried.
        if done is None:
            SeedCheckpoint.objects.create(key=CHECKPOINT, detail=summary)
        for conflict in stats["conflicts"]:
            self.stderr.write(self.style.WARNING(conflict + " 已跳过该条，请在后台核对。"))
        self.stdout.write(self.style.SUCCESS(summary))

    def copy_asset(self, relative):
        root = (settings.BASE_DIR / "seed").resolve()
        source = (root / relative).resolve()
        if not source.is_relative_to(root) or not source.is_file():
            raise CommandError(f"初始素材缺失：{relative}")
        name = f"initial/{relative}"
        target = Path(settings.MEDIA_ROOT) / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            shutil.copyfile(source, target)
        return name
