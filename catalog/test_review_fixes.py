import io
from pathlib import Path
from urllib.parse import unquote
from zipfile import ZipFile

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from pypdf import PdfWriter

from .exporting import website_archive
from .models import HomeSlide, Resource, Publication, Figure
from .test_research import MediaMixin
from .validators import pdf_metadata


@override_settings(ALLOWED_HOSTS=['testserver'])
class ReviewRegressionTests(MediaMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        for command in ('seed_site', 'seed_publications', 'seed_home_slides'):
            call_command(command, stdout=io.StringIO())
        cls.owner = get_user_model().objects.create_superuser('review-owner', password='Review-only-2026')

    def test_supplied_pdfs_read_without_changing_bytes(self):
        for path in (settings.BASE_DIR / 'seed/documents').glob('*.pdf'):
            with self.subTest(path=path.name):
                original = path.read_bytes()
                file = SimpleUploadedFile(path.name, original)
                pages, size = pdf_metadata(file)
                self.assertGreater(pages, 0)
                self.assertEqual(size, len(original))
                self.assertEqual(file.read(), original)

    def test_actual_open_password_and_bad_pdf_still_rejected(self):
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        writer.encrypt('required-password', algorithm='AES-256')
        stream = io.BytesIO()
        writer.write(stream)
        with self.assertRaisesMessage(ValidationError, '密码保护'):
            pdf_metadata(SimpleUploadedFile('locked.pdf', stream.getvalue()))
        with self.assertRaises(ValidationError):
            pdf_metadata(SimpleUploadedFile('bad.pdf', b'%PDF-not-a-document'))

    def test_withdrawn_sources_hide_slides_and_export(self):
        slide = HomeSlide.objects.filter(source_figure__isnull=False).first()
        figure = slide.source_figure
        publication = figure.publication
        for source in (slide.source_direction, figure, publication):
            with self.subTest(source=type(source).__name__):
                source.is_published = False
                source.save()
                self.assertNotContains(self.client.get('/index.html'), f'id="home-slide-{slide.pk}"')
                with website_archive() as stream, ZipFile(stream) as archive:
                    self.assertNotIn(f'id="home-slide-{slide.pk}"', archive.read('index.html').decode())
                source.is_published = True
                source.save()
        figure.delete()
        self.assertFalse(HomeSlide.objects.filter(pk=slide.pk).exists())

    def test_media_access_is_reference_and_permission_scoped(self):
        resource = Resource.objects.exclude(document='').first()
        url = resource.document.url
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['Cache-Control'], 'private, no-store')
        response.close()
        resource.is_published = False
        resource.save()
        self.assertEqual(self.client.get(url).status_code, 404)
        staff = get_user_model().objects.create_user('staff-without-model-access', is_staff=True)
        self.client.force_login(staff, backend='django.contrib.auth.backends.ModelBackend')
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.force_login(self.owner, backend='django.contrib.auth.backends.ModelBackend')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        response.close()
        self.client.logout()
        publication = Publication.objects.create(title='共享原文', year=2026, document=resource.document.name, is_published=True)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn(publication.download_name, unquote(response.headers['Content-Disposition']))
        response.close()
        publication.delete()
        resource.document = ''
        resource.source_url = 'https://example.com/review'
        resource.save(update_fields=['document', 'source_url'])
        resource.refresh_from_db()
        self.assertEqual((resource.pages, resource.file_bytes), (0, 0))
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertTrue((Path(settings.MEDIA_ROOT) / url.removeprefix('/media/')).exists())

    def test_figure_and_carousel_do_not_keep_withdrawn_media_public(self):
        slide = HomeSlide.objects.filter(source_figure__isnull=False).first()
        url = slide.photo.url
        slide.source_figure.publication.is_published = False
        slide.source_figure.publication.save()
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_empty_carousel_still_has_stable_heading(self):
        HomeSlide.objects.update(is_published=False)
        response = self.client.get('/index.html')
        self.assertContains(response, '<h1 class="visually-hidden">', count=1)
        self.assertNotContains(response, 'data-carousel role=')

    def test_resource_duplicate_error_and_controlled_existing_types(self):
        self.client.force_login(self.owner, backend='django.contrib.auth.backends.ModelBackend')
        resource = Resource.objects.first()
        resource.source_url = 'https://example.com/already-used'
        resource.save()
        response = self.client.post('/manage/catalog/resource/add/', {
            'title': '审查资料', 'kind': resource.kind, 'disease': '肺炎', 'position': 100,
            'source_url': resource.source_url})
        self.assertEqual(response.status_code, 200)
        self.assertIn('source_url', response.context['adminform'].form.errors)
        self.assertContains(response, '该原文或课程链接已被另一份学习资料使用')
        form = self.client.get('/manage/catalog/resource/add/').context['adminform'].form
        existing = set(Resource.objects.values_list('kind', flat=True))
        self.assertEqual({value for value, label in form.fields['kind'].choices if value}, existing)
        self.assertContains(self.client.get('/index.html'), '全部学习资料 →')

    def test_source_visibility_status_and_cascade_delete_notices(self):
        self.client.force_login(self.owner, backend='django.contrib.auth.backends.ModelBackend')
        slide = HomeSlide.objects.filter(source_figure__isnull=False).first()
        sources = [(slide.source_direction, '来源研究方向未公开'),
                   (slide.source_figure, '来源配图未公开'),
                   (slide.source_figure.publication, '来源配图所属成果未公开')]
        for source, message in sources:
            source.is_published = False
            source.save()
            self.assertContains(self.client.get(f'/manage/catalog/homeslide/{slide.pk}/change/'), message)
            self.assertContains(self.client.get('/manage/catalog/homeslide/'), message)
            response = self.client.get(f'/manage/catalog/{source._meta.model_name}/{source.pk}/delete/')
            self.assertContains(response, '此操作会删除 1 张首页轮播')
            self.assertContains(response, slide.title)
            source.is_published = True
            source.save()
        response = self.client.post('/manage/catalog/figure/',
                                    {'action': 'delete_selected', '_selected_action': [slide.source_figure_id]})
        self.assertContains(response, '此操作会删除 1 张首页轮播')
        self.assertTrue(HomeSlide.objects.filter(pk=slide.pk).exists())

    def test_similar_url_warns_without_rewriting_or_forcing_a_merge(self):
        self.client.force_login(self.owner, backend='django.contrib.auth.backends.ModelBackend')
        existing = Resource.objects.first()
        existing.source_url = 'https://example.com/guidance'
        existing.save()
        original = 'http://EXAMPLE.COM/guidance/'
        response = self.client.post('/manage/catalog/resource/add/', {
            'title': '另一个来源', 'kind': existing.kind, 'disease': '肺炎', 'position': 100,
            'source_url': original}, follow=True)
        self.assertContains(response, '链接可能指向相同内容')
        self.assertContains(response, existing.title)
        self.assertTrue(Resource.objects.filter(source_url=original).exists())
        existing.refresh_from_db()
        self.assertEqual(existing.source_url, 'https://example.com/guidance')

    def test_pdf_filename_bounds_preserve_title_and_windows_path_margin(self):
        resource = Resource(title='Long original scientific title ' * 20)
        original = resource.title
        self.assertLessEqual(len(resource.download_name), 100)
        self.assertLessEqual(len(resource.download_name.encode()), 184)
        self.assertLess(len('C:/Users/Customer Name/Downloads/caobin-lab-offline/caobin-lab-offline/media/initial/documents/'
                            + resource.download_name), 260)
        self.assertEqual(resource.title, original)
