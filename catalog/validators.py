from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4
from PIL import Image
from pypdf import PdfReader
from pypdf.errors import PdfReadError
from django.core.exceptions import ValidationError


def upload_path(instance, filename):
    return f"uploads/{uuid4().hex}{Path(filename).suffix.lower()}"


def validate_image(file):
    if file.size > 10 * 1024 * 1024:
        raise ValidationError("图片不能超过 10 MB。")
    if Path(file.name).suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp"):
        raise ValidationError("请上传 JPG、PNG 或 WebP 图片。")
    try:
        file.open("rb")
        with Image.open(file) as image:
            if image.format not in ("JPEG", "PNG", "WEBP") or image.width * image.height > 40_000_000:
                raise ValidationError("图片格式不支持或尺寸超过 4000 万像素。")
            image.verify()
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        raise ValidationError("图片无法读取，请重新导出图片。") from exc
    finally:
        file.open("rb")
        file.seek(0)


def pdf_metadata(file):
    if file.size > 40 * 1024 * 1024 or Path(file.name).suffix.lower() != ".pdf":
        raise ValidationError("请上传不超过 40 MB 的 PDF 文件。")
    try:
        file.open("rb")
        if file.read(5) != b"%PDF-":
            raise ValidationError("文件内容不是有效的 PDF。")
        file.seek(0)
        reader = PdfReader(file, strict=False)
        if reader.is_encrypted:
            raise ValidationError("请先解除 PDF 密码保护。")
        pages = len(reader.pages)
        if not pages:
            raise ValidationError("PDF 中没有可阅读页面。")
        return pages, file.size
    except (PdfReadError, OSError, ValueError) as exc:
        raise ValidationError("PDF 无法解析，请检查原文件。") from exc
    finally:
        file.open("rb")
        file.seek(0)


def validate_pdf(file):
    pdf_metadata(file)


def validate_web_url(value):
    if value and urlsplit(value).scheme not in ("http", "https"):
        raise ValidationError("链接必须以 https:// 或 http:// 开头。")
