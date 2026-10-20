import json
import shutil
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from catalog.models import SiteSettings, Page, ResearchDirection, Project, Member, Publication, Resource


class Command(BaseCommand):
    help = "首次初始化网站内容；已有数据时跳过，不覆盖后台编辑。"

    @transaction.atomic
    def handle(self, *args, **options):
        if SiteSettings.objects.exists():
            self.stdout.write("已有网站数据，跳过初始化。")
            return
        if any(model.objects.exists() for model in (Page, ResearchDirection, Project, Member, Publication, Resource)):
            raise CommandError("检测到部分内容，停止初始化以免覆盖。请恢复备份或检查数据库。")
        source = settings.BASE_DIR / "seed"
        data = json.loads((source / "content.json").read_text(encoding="utf-8"))

        def asset(relative):
            if not relative:
                return ""
            source_file = (source / relative).resolve()
            if not source_file.is_relative_to(source.resolve()) or not source_file.is_file():
                raise CommandError(f"初始素材缺失：{relative}")
            name = f"initial/{relative}"
            target = Path(settings.MEDIA_ROOT) / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source_file, target)
            return name

        leader = data["leader"]
        SiteSettings.objects.create(
            pk=1, name=data["name"], subtitle=data["subtitle"],
            hero_title="呼吸道感染与临床转化研究",
            hero_english="Respiratory Infection & Translational Research",
            hero_intro="围绕病毒性肺炎、呼吸道病原体、抗病毒药物评价与微生物组，开展临床研究与转化探索。",
            hero_photo=asset(leader["photo"]), leader_name=leader["name"], leader_english="Bin Cao",
            leader_role=leader["role"], leader_bio="\n\n".join(leader["bio"]),
            leader_photo=asset(leader["photo"]), contact_name=data["contact"]["name"],
            contact_email=data["contact"]["email"],
        )
        english = ["Home", "Research", "Publications", "Our Team", "Learning Resources", "Contact"]
        introductions = ["", "围绕呼吸道感染的临床问题，连接病原、宿主与转化研究。",
                         "科研项目、研究论文与其他科研成果。", "",
                         "常见呼吸疾病的指南、专家共识与学习资料。点击卡片阅读 PDF，也可下载保存。",
                         "欢迎开展呼吸道感染与临床转化研究相关的学术交流。"]
        for (slug, title), en, intro in zip(Page.ROUTES, english, introductions):
            Page.objects.create(slug=slug, title=title, english=en, intro=intro)
        for i, item in enumerate(data["research"]):
            ResearchDirection.objects.create(**item, position=i, is_published=True)
        for i, item in enumerate(data["projects"]):
            Project.objects.create(**item, position=i, is_published=True)
        for i, name in enumerate(data["members"]):
            Member.objects.create(name=name, group="faculty", position=i, is_published=True)
        for i, item in enumerate(data["trainees"]):
            fields = {key: item.get(key, "") for key in ("name", "group", "stage", "school", "workplace", "cohort")}
            if fields["cohort"].isdigit():
                fields["cohort"] += "级"
            Member.objects.create(**fields, photo=asset(item["photo"]), position=i, is_published=True)
        for i, item in enumerate(data["resources"]):
            Resource.objects.create(
                title=item["title"], english=item.get("english", ""), kind=item["kind"],
                disease=item["disease"], year=item["year"], version_label=item.get("version", ""),
                journal=item["journal"], document=asset(item["path"]), cover=asset(item["cover"]),
                pages=item["pages"], file_bytes=item["bytes"], position=i, is_published=True,
            )
        self.stdout.write(self.style.SUCCESS("已导入 6 个研究方向、4 个项目、49 位团队成员和 9 份学习资料。"))
