"""Remove the withdrawn learning-resource categories once, retaining shared media."""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from catalog.models import Resource, SeedCheckpoint


RETIRED_KINDS = (
    '书籍介绍', '学习心得', '学术活动', '病例讨论',
    '研究文献', '研究进展', '科普文章', '视频课程',
)


class Command(BaseCommand):
    help = '删除已撤下的八类学习资料记录；保留指南、其他历史草稿及共享文件。'

    @transaction.atomic
    def handle(self, *args, **options):
        key = 'remove-retired-resources-20261109'
        if SeedCheckpoint.objects.filter(key=key).exists():
            self.stdout.write('后台资料已清理，保留后续编辑。')
            return
        records = list(Resource.objects.select_for_update().filter(kind__in=RETIRED_KINDS))
        if any(item.is_published for item in records):
            raise CommandError('待删除类型中仍有公开资料，请先核对撤下范围；未删除任何记录。')
        # Django keeps FileField storage on deletion. Publications may share these files.
        count, _ = Resource.objects.filter(pk__in=[item.pk for item in records]).delete()
        summary = f'已删除 {count} 条已撤下的学习资料记录，保留共享文件及其他内容。'
        SeedCheckpoint.objects.create(key=key, detail=summary)
        self.stdout.write(summary)
