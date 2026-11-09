import io
from datetime import date
from importlib import import_module
from zipfile import ZipFile

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import connection
from django.test import TestCase, override_settings
from PIL import Image

from .exporting import website_archive
from .models import News, Page
from .test_research import MediaMixin


@override_settings(ALLOWED_HOSTS=['testserver'])
class NewsTests(MediaMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_site', stdout=io.StringIO())
        cls.admin = get_user_model().objects.create_superuser('news-editor', password='test-password')

    def login(self):
        self.client.force_login(self.admin, backend='django.contrib.auth.backends.ModelBackend')

    def test_empty_page_navigation_and_existing_install_page_creation(self):
        self.assertEqual(News.objects.count(), 0)
        response = self.client.get('/news.html')
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'class="news-entry"')
        self.assertNotContains(response, '示例')
        nav = response.content.decode().split('id="site-nav"')[1].split('</nav>')[0]
        self.assertLess(nav.index('resources.html'), nav.index('news.html'))
        self.assertLess(nav.index('news.html'), nav.index('contact.html'))
        migration = import_module('catalog.migrations.0015_academic_news')
        Page.objects.get(slug='news').delete()
        schema_editor = connection.schema_editor()
        migration.add_news_page(apps, schema_editor)
        Page.objects.filter(slug='news').update(title='团队自定义名称')
        migration.add_news_page(apps, schema_editor)
        self.assertEqual(Page.objects.get(slug='news').title, '团队自定义名称')

    def test_publication_media_permissions_and_offline_export(self):
        image = io.BytesIO()
        Image.new('RGB', (8, 8), 'blue').save(image, 'PNG')
        obj = News.objects.create(title='测试动态 <script>alert(1)</script>', text='第一段\n\n第二段',
                                  photo=SimpleUploadedFile('news.png', image.getvalue(), content_type='image/png'))
        url = obj.photo.url
        self.assertNotContains(self.client.get('/news.html'), '第一段')
        self.assertEqual(self.client.get(url).status_code, 404)
        with website_archive() as stream, ZipFile(stream) as archive:
            self.assertIn('news.html', archive.namelist())
            self.assertNotIn('media/' + obj.photo.name, archive.namelist())
        self.login()
        self.assertEqual(self.client.get(url).status_code, 200)
        self.client.logout()
        obj.is_published = True
        obj.save()
        html = self.client.get('/news.html')
        self.assertContains(html, '&lt;script&gt;alert(1)&lt;/script&gt;')
        self.assertContains(html, '<p>第一段</p>')
        self.assertEqual(self.client.get(url).status_code, 200)
        with website_archive() as stream, ZipFile(stream) as archive:
            self.assertEqual(archive.read('media/' + obj.photo.name), image.getvalue())
            self.assertIn('第一段', archive.read('news.html').decode())
        obj.delete()
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_admin_create_edit_conflict_unpublish_delete_and_permission(self):
        add = '/manage/catalog/news/add/'
        self.assertEqual(self.client.get(add).status_code, 302)
        staff = get_user_model().objects.create_user('no-permission', is_staff=True)
        self.client.force_login(staff, backend='django.contrib.auth.backends.ModelBackend')
        self.assertEqual(self.client.get(add).status_code, 403)
        self.login()
        data = {'title': '测试动态', 'published_on': '2026-11-09', 'text': '测试正文',
                'position': 100, 'is_published': 'on', '_save': '保存'}
        self.assertEqual(self.client.post(add, data).status_code, 302)
        obj = News.objects.get()
        change = f'/manage/catalog/news/{obj.pk}/change/'
        self.assertContains(self.client.get(change), '/news.html')
        data.update(title='修改后标题', edit_version=obj.version)
        self.assertEqual(self.client.post(change, data).status_code, 302)
        stale = self.client.post(change, {**data, 'title': '过期修改'})
        self.assertContains(stale, '另一个窗口修改或删除')
        obj.refresh_from_db()
        self.assertEqual(obj.title, '修改后标题')
        data.update(edit_version=obj.version)
        data.pop('is_published')
        self.assertEqual(self.client.post(change, data).status_code, 302)
        self.assertNotContains(self.client.get('/news.html'), '修改后标题')
        self.assertEqual(self.client.post(f'/manage/catalog/news/{obj.pk}/delete/', {'post': 'yes'}).status_code, 302)
        self.assertFalse(News.objects.exists())

    def test_order_and_invalid_link(self):
        newer = News.objects.create(title='较新', published_on=date(2026, 11, 9), is_published=True)
        older = News.objects.create(title='优先', published_on=date(2025, 1, 1), position=1, is_published=True)
        self.assertEqual(list(News.objects.all()), [older, newer])
        newer.source_url = 'javascript:alert(1)'
        with self.assertRaises(ValidationError):
            newer.full_clean()
