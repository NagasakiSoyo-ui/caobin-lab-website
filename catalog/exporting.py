import re
from pathlib import Path
from tempfile import SpooledTemporaryFile
from urllib.parse import unquote
from zipfile import ZipFile, ZIP_DEFLATED
from django.conf import settings
from django.db import transaction
from .presentation import website_context, render_website


def website_archive():
    # One database snapshot keeps the six exported pages mutually consistent.
    with transaction.atomic():
        shared = website_context("index")
        documents = {}
        media = set()
        for page in shared["pages"]:
            context = {**shared, "page": page, "route": page.slug}
            html = render_website(page.slug, context)
            media.update(unquote(url) for url in re.findall(r'(?:src|href)="(/media/[^"]+)"', html))
            html = html.replace('/static/site/', 'assets/').replace('/media/', 'media/')
            documents[f"{page.slug}.html"] = html
    stream = SpooledTemporaryFile(max_size=8 * 1024 * 1024)
    try:
        with ZipFile(stream, "w", ZIP_DEFLATED, compresslevel=6) as archive:
            for name, html in documents.items():
                archive.writestr(name, html)
            for file in (settings.BASE_DIR / "static/site").rglob("*"):
                if file.is_file():
                    archive.write(file, "assets/" + file.relative_to(settings.BASE_DIR / "static/site").as_posix())
            media_root = Path(settings.MEDIA_ROOT).resolve()
            for url in sorted(media):
                relative = url.removeprefix("/media/")
                file = (media_root / relative).resolve()
                if not file.is_relative_to(media_root) or not file.is_file():
                    raise FileNotFoundError(f"导出中发现缺失的素材：{relative}")
                archive.write(file, "media/" + relative)
            archive.writestr("打开网站.txt", "完整解压后双击 index.html。\n请整体保留 assets 与 media 文件夹。\n这是前台离线快照；后台管理需运行服务端。\n")
        stream.seek(0)
        return stream
    except Exception:
        stream.close()
        raise
