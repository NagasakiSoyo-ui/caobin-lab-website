"""Initialize additional slides from existing, published team content; never rewrite source text."""
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from catalog.models import HomeSlide, ResearchDirection, SeedCheckpoint
from catalog.presentation import public_figures


class Command(BaseCommand):
    help = "首次增加三张首页轮播，直接使用现有研究方向原文及论文原图；后续启动保留后台修改。"

    @transaction.atomic
    def handle(self, *args, **options):
        key = 'home-carousel-20261106'
        if SeedCheckpoint.objects.filter(key=key).exists():
            self.stdout.write('首页轮播已初始化，保留后台后续修改。')
            return
        selected = [('viral-sepsis', 'pmid32311318-figure.jpg'),
                    ('pathogen-diagnosis', 'pmid39692191-fig1.jpg'),
                    ('microbiome', 'pmid40858544-fig6.jpg')]
        created = 0
        for position, (slug, filename) in enumerate(selected, 1):
            direction = ResearchDirection.objects.filter(slug=slug, is_published=True).first()
            if not direction:
                continue  # A direction withdrawn by the editor must not be republished via a slide.
            figure = public_figures().filter(directions=direction, image=f'initial/figures/{filename}').first()
            if not figure:
                continue
            if not (Path(settings.MEDIA_ROOT) / figure.image.name).is_file():
                raise CommandError(f'首页轮播原图缺失：{figure.image.name}')
            HomeSlide.objects.create(title=direction.title, intro=direction.text, photo=figure.image.name,
                                     image_fit='contain', position=position, is_published=True)
            created += 1
        SeedCheckpoint.objects.create(key=key, detail=f'首页轮播新增 {created} 张；标题和介绍取自现有研究方向，图片取自已公开论文原图。')
        self.stdout.write(f'首页轮播新增 {created} 张。')
