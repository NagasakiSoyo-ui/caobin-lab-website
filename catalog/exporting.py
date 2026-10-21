import re
from html.parser import HTMLParser
from pathlib import Path
from tempfile import SpooledTemporaryFile
from urllib.parse import unquote, urlsplit
from zipfile import ZipFile, ZIP_DEFLATED
from django.conf import settings
from django.db import transaction
from django.template.loader import render_to_string
from .presentation import website_context, page_manifest

# URL-bearing attributes. srcset holds a comma-separated list of "url descriptor" entries,
# so each URL in it is handled separately. Only URLs that start with the site-local prefixes
# are rewritten; external URLs that merely contain "/media/" or "/static/" are left untouched.
URL_ATTRIBUTE = re.compile(r'\b(src|href|data-full|srcset)="([^"]*)"')
LOCAL_PREFIXES = (("/media/", "media/"), ("/static/site/", "assets/"))


def srcset_urls(value):
    return [entry.split()[0] for entry in value.split(",") if entry.strip()]


def attribute_urls(html):
    for name, value in URL_ATTRIBUTE.findall(html):
        yield from (srcset_urls(value) if name == "srcset" else [value])


def _local(url):
    for prefix, replacement in LOCAL_PREFIXES:
        if url.startswith(prefix):
            return replacement + url[len(prefix):]
    return url


def _rewrite(match):
    name, value = match.groups()
    if name == "srcset":
        entries = []
        for entry in value.split(","):
            parts = entry.strip().split(None, 1)
            if parts:
                entries.append(" ".join([_local(parts[0])] + parts[1:]))
        value = ", ".join(entries)
    else:
        value = _local(value)
    return f'{name}="{value}"'


def media_references(html):
    return {unquote(url) for url in attribute_urls(html) if url.startswith("/media/")}


class LinkCollector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links, self.ids = [], set()

    def handle_starttag(self, tag, attrs):
        for name, value in attrs:
            if name == "id" and value:
                self.ids.add(value)
            if name in ("href", "src", "data-full") and value:
                self.links.append(value)
            if name == "srcset" and value:
                self.links.extend(srcset_urls(value))


def localize(html):
    return URL_ATTRIBUTE.sub(_rewrite, html)


def check_links(documents, files):
    """Every relative link in the exported pages must resolve inside the archive (and its #id)."""
    parsed = {}
    for name, html in documents.items():
        collector = LinkCollector()
        collector.feed(html)
        parsed[name] = collector
    broken = []
    for name, collector in parsed.items():
        for link in collector.links:
            parts = urlsplit(link)
            if parts.scheme in ("http", "https", "mailto", "tel", "data"):
                continue
            if parts.scheme or link.startswith("/"):
                broken.append(f"{name}: 非离线路径 {link}")
                continue
            target = unquote(parts.path) or name
            if target not in files:
                broken.append(f"{name}: 缺少 {target}")
            elif parts.fragment and target in parsed and parts.fragment not in parsed[target].ids:
                broken.append(f"{name}: {target} 中没有锚点 #{parts.fragment}")
    if broken:
        raise ValueError("离线包链接校验失败：\n" + "\n".join(broken[:30]))


def website_archive():
    # One database snapshot keeps all exported pages mutually consistent.
    with transaction.atomic():
        documents, media = {}, set()
        for filename, template, context in page_manifest(website_context("index")):
            html = render_to_string(template, context)
            media.update(media_references(html))
            documents[filename] = localize(html)
    static_root = settings.BASE_DIR / "static/site"
    static_files = {"assets/" + f.relative_to(static_root).as_posix(): f for f in static_root.rglob("*") if f.is_file()}
    media_root = Path(settings.MEDIA_ROOT).resolve()
    media_files = {}
    for url in sorted(media):
        relative = url.removeprefix("/media/")
        file = (media_root / relative).resolve()
        if not file.is_relative_to(media_root) or not file.is_file():
            raise FileNotFoundError(f"导出中发现缺失的素材：{relative}")
        media_files["media/" + relative] = file
    check_links(documents, set(documents) | set(static_files) | set(media_files))
    stream = SpooledTemporaryFile(max_size=8 * 1024 * 1024)
    try:
        with ZipFile(stream, "w", ZIP_DEFLATED, compresslevel=6) as archive:
            for name, html in documents.items():
                archive.writestr(name, html)
            for name, file in {**static_files, **media_files}.items():
                archive.write(file, name)
            archive.writestr("打开网站.txt", "完整解压后双击 index.html。\n请整体保留 assets 与 media 文件夹。\n"
                             "研究配图为原文原图，点击图片可查看大图；图片说明下方注明原文出处。\n"
                             "这是前台离线快照；后台管理需运行服务端。\n")
        stream.seek(0)
        return stream
    except Exception:
        stream.close()
        raise
