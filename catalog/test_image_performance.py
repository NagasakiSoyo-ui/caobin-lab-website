import io
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from zipfile import ZipFile

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from PIL import Image

from .exporting import website_archive
from .image_previews import image_preview
from .models import Member
from .test_research import MediaMixin


@override_settings(ALLOWED_HOSTS=['testserver'])
class ImagePerformanceTests(MediaMixin, TestCase):
    def setUp(self):
        self.settings = override_settings(DATA_DIR=Path(self.temporary.name))
        self.settings.enable()
        self.addCleanup(self.settings.disable)
        buffer = io.BytesIO()
        Image.new('RGB', (1600, 2400), '#526b82').save(buffer, 'JPEG')
        self.original = buffer.getvalue()
        self.member = Member.objects.create(name='测试照片', group='faculty', is_published=True,
            photo=SimpleUploadedFile('portrait.jpg', self.original, content_type='image/jpeg'))

    def test_preview_keeps_original_and_revalidates_after_permissions(self):
        url = self.member.photo.url + '?width=640'
        response = self.client.get(url)
        image = b''.join(response.streaming_content)
        etag = response.headers['ETag']
        self.assertEqual(response['Content-Type'], 'image/webp')
        self.assertEqual(response['Cache-Control'], 'private, no-cache')
        self.assertEqual(Image.open(io.BytesIO(image)).size, (640, 960))
        self.assertEqual(Path(self.member.photo.path).read_bytes(), self.original)
        cached = self.client.get(url, HTTP_IF_NONE_MATCH=etag)
        self.assertEqual(cached.status_code, 304)
        self.assertEqual(cached.content, b'')
        self.member.is_published = False
        self.member.save()
        self.assertEqual(self.client.get(url, HTTP_IF_NONE_MATCH=etag).status_code, 404)
        self.assertEqual(self.client.get('/media/../secret.key?width=640').status_code, 404)

    def test_original_images_cache_without_changing_bytes_and_bad_size_rejected(self):
        response = self.client.get(self.member.photo.url)
        self.assertEqual(b''.join(response.streaming_content), self.original)
        self.assertEqual(self.client.get(self.member.photo.url, HTTP_IF_NONE_MATCH=response['ETag']).status_code, 304)
        for width in ('0', '99999', 'bad', ''):
            self.assertEqual(self.client.get(self.member.photo.url + '?width=' + width).status_code, 400)

    def test_replacement_invalidates_preview_and_concurrent_generation_is_complete(self):
        source = Path(self.member.photo.path)
        first = image_preview(source, 640)
        Image.new('RGB', (800, 1200), '#aaccee').save(source, 'JPEG')
        with ThreadPoolExecutor(max_workers=4) as pool:
            copies = list(pool.map(lambda _: image_preview(source, 640), range(4)))
        self.assertNotEqual(first, copies[0])
        self.assertEqual(len(set(copies)), 1)
        self.assertEqual(Image.open(copies[0]).size, (640, 960))
        self.assertFalse(list(copies[0].parent.glob('tmp*.webp')))

    def test_export_resolves_previews_and_preserves_other_links(self):
        # Seed before adding the fixture to exercise the real render/export path.
        self.member.delete()
        call_command('seed_site', stdout=io.StringIO())
        member = Member.objects.exclude(photo='').first()
        original = Path(member.photo.path).read_bytes()
        with website_archive() as stream, ZipFile(stream) as archive:
            html = archive.read('team.html').decode()
            self.assertNotIn('?width=', html)
            previews = [name for name in archive.namelist() if name.startswith('media/previews/')]
            self.assertTrue(previews)
            for name in previews:
                self.assertLessEqual(Image.open(io.BytesIO(archive.read(name))).width, 640)
        self.assertEqual(Path(member.photo.path).read_bytes(), original)
