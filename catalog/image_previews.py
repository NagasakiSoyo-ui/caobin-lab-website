"""Small display copies; originals and their permission checks remain authoritative."""
import hashlib
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from django.conf import settings
from PIL import Image, ImageOps

PREVIEW_WIDTHS = (640,)


def image_preview(source, width):
    if width not in PREVIEW_WIDTHS or source.suffix.lower() not in ('.jpg', '.jpeg', '.png', '.webp'):
        raise ValueError('Unsupported image preview')
    stat = source.stat()
    key = hashlib.sha256(f'v1:{source}:{stat.st_mtime_ns}:{stat.st_size}:{width}'.encode()).hexdigest()
    folder = Path(settings.DATA_DIR) / 'image-cache'
    target = folder / f'{key}.webp'
    if target.exists():
        return target
    folder.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as original:
        image = ImageOps.exif_transpose(original)
        # Never crop or upscale; retain transparency and the original colour profile.
        image.thumbnail((width, max(1, round(width * image.height / image.width))), Image.Resampling.LANCZOS)
        if image.mode not in ('RGB', 'RGBA'):
            image = image.convert('RGBA' if 'transparency' in image.info else 'RGB')
        with NamedTemporaryFile(dir=folder, suffix='.webp', delete=False) as temporary:
            temp = Path(temporary.name)
        try:
            image.save(temp, 'WEBP', quality=85, method=4, icc_profile=original.info.get('icc_profile', b''))
            try:
                # Atomic publication: Windows keeps a concurrent winner; POSIX may
                # replace it with the same complete image without affecting readers.
                os.rename(temp, target)
            except FileExistsError:
                pass
        finally:
            temp.unlink(missing_ok=True)
    return target
