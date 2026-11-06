from pathlib import Path
from zipfile import ZipFile
from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from .exporting import website_archive
from .models import Figure, HomeSlide, Member, Page, Project, Publication, ResearchDirection, Resource, SiteSettings
from .test_research import MediaMixin
from pypdf import PdfReader


@override_settings(ALLOWED_HOSTS=["testserver"])
class ImageEditingTests(MediaMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_site", verbosity=0)
        call_command("seed_publications", verbosity=0)
        cls.owner = get_user_model().objects.create_superuser("image-editor", password="Test-images-only-2026")

    def setUp(self):
        self.client.force_login(self.owner, backend="django.contrib.auth.backends.ModelBackend")

    def image(self):
        original = settings.BASE_DIR / "seed/figures/pmid32311318-figure.jpg"
        return SimpleUploadedFile("image.jpg", original.read_bytes(), content_type="image/jpeg")

    def url(self, obj, action="change"):
        return f"/manage/catalog/{obj._meta.model_name}/{obj.pk}/{action}/"

    def payload(self, obj):
        form = self.client.get(self.url(obj)).context["adminform"].form
        return {name: ("on" if value is True else "" if value is None or value is False else value)
                for name, field in form.fields.items() if not isinstance(field, forms.FileField)
                for value in [form[name].value()]}

    def test_saved_page_links_are_local_and_drafts_use_the_listing(self):
        cases = [(SiteSettings.objects.first(), '/index.html'), (Page.objects.get(slug='team'), '/team.html'),
                 (Member.objects.first(), '/team.html'), (Project.objects.first(), '/projects.html'),
                 (Publication.objects.first(), '/publications.html'), (Resource.objects.first(), '/resources.html')]
        direction = ResearchDirection.objects.filter(is_published=True).first()
        cases.append((direction, f'/research-{direction.slug}.html'))
        for obj, url in cases:
            with self.subTest(model=type(obj).__name__):
                response = self.client.get(self.url(obj))
                self.assertEqual(response.context['saved_page_url'], url)
                self.assertContains(response, '查看已保存页面')
        direction.is_published = False
        direction.save()
        self.assertEqual(self.client.get(self.url(direction)).context['saved_page_url'], '/research.html')

    def test_invalid_save_keeps_text_and_original_image_and_reports_failure(self):
        member = Member.objects.exclude(photo='').first()
        image = member.photo.name
        data = {**self.payload(member), 'position': '-1', 'bio': '保留本次未保存的输入'}
        response = self.client.post(self.url(member), data)
        self.assertContains(response, '本次保存未成功')
        self.assertContains(response, '保留本次未保存的输入')
        self.assertContains(response, '请重新选择后保存')
        member.refresh_from_db()
        self.assertNotEqual(member.bio, data['bio'])
        self.assertEqual(member.photo.name, image)

    def test_publication_uses_shared_image_manager_and_prefills_parent(self):
        publication = Publication.objects.filter(figures__isnull=False).first()
        response = self.client.get(self.url(publication))
        self.assertContains(response, 'class="direction-image-manager"')
        self.assertContains(response, publication.figures.first().image.url)
        add_url = f'/manage/catalog/figure/add/?publication={publication.pk}'
        self.assertContains(response, add_url)
        self.assertEqual(str(self.client.get(add_url).context['adminform'].form['publication'].value()), str(publication.pk))

    def test_figure_delete_explains_all_associations_and_bulk_scope(self):
        figure = Figure.objects.first()
        directions = list(ResearchDirection.objects.all()[:2])
        figure.directions.set(directions)
        response = self.client.get(self.url(figure, 'delete'))
        self.assertContains(response, '删除整张配图会从所有关联研究方向撤下')
        for direction in directions:
            self.assertContains(response, direction.title)
        response = self.client.post('/manage/catalog/figure/', {'action': 'delete_selected', '_selected_action': [figure.pk]})
        self.assertContains(response, '取消勾选该方向后保存')
        self.assertTrue(Figure.objects.filter(pk=figure.pk).exists())

    def test_figure_reordering_updates_direction_and_survives_stale_submission(self):
        direction = ResearchDirection.objects.first()
        figures = list(Figure.objects.filter(is_published=True, publication__is_published=True)[:2])
        for index, figure in enumerate(figures):
            figure.directions.add(direction)
            figure.position = 100 + index
            figure.save()
        figure = figures[1]
        stale = self.payload(figure)
        response = self.client.post(self.url(figure), {**stale, 'position': 0})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(direction.figures.first().pk, figure.pk)
        response = self.client.post(self.url(figure), {**stale, 'position': 500})
        self.assertContains(response, '这条内容已被另一个窗口修改或删除')
        figure.refresh_from_db()
        self.assertEqual(figure.position, 0)

    def test_all_optional_images_add_replace_clear_and_export(self):
        cases = [(HomeSlide.objects.first(), "photo", "/index.html"),
                 (SiteSettings.objects.get(pk=1), "leader_photo", "/team.html"),
                 (Member.objects.filter(is_published=True).first(), "photo", "/team.html"),
                 (Resource.objects.filter(is_published=True).first(), "cover", "/resources.html")]
        for obj, field, page in cases:
            with self.subTest(field=field):
                html = self.client.get(self.url(obj)).content.decode()
                self.assertIn('class="image-upload"', html)
                self.assertIn('admin-image-preview.js', html)
                for _ in range(2):  # first add/replace, then replace the uploaded file
                    obj.refresh_from_db()
                    previous = getattr(obj, field).name
                    response = self.client.post(self.url(obj), {**self.payload(obj), field: self.image()})
                    self.assertEqual(response.status_code, 302, response.context['adminform'].form.errors if response.status_code == 200 else '')
                    obj.refresh_from_db()
                    current = getattr(obj, field)
                    self.assertNotEqual(previous, current.name)
                    self.assertContains(self.client.get(page), current.url)
                removed_url, removed_name = current.url, current.name
                self.assertEqual(self.client.post(self.url(obj), {**self.payload(obj), field + "-clear": "on"}).status_code, 302)
                obj.refresh_from_db()
                self.assertFalse(getattr(obj, field))
                self.assertNotContains(self.client.get(page), removed_url)
                with website_archive() as stream, ZipFile(stream) as archive:
                    self.assertNotIn("media/" + removed_name, archive.namelist())
                # Adding again from an empty field must also work.
                self.assertEqual(self.client.post(self.url(obj), {**self.payload(obj), field: self.image()}).status_code, 302)

    def test_invalid_and_conflicting_upload_keeps_existing_image(self):
        member = Member.objects.exclude(photo="").first()
        original = member.photo.name
        for file, extra in [(SimpleUploadedFile("bad.jpg", b"not an image"), {}),
                            (self.image(), {"photo-clear": "on"})]:
            response = self.client.post(self.url(member), {**self.payload(member), "photo": file, **extra})
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.context["adminform"].form.errors)
            member.refresh_from_db()
            self.assertEqual(member.photo.name, original)

    def test_existing_protected_pdf_does_not_block_cover_edit_but_new_upload_is_checked(self):
        resource = Resource.objects.get(document="initial/documents/resource-05.pdf")
        with resource.document.open("rb") as file:
            original = file.read()
        import io
        self.assertTrue(PdfReader(io.BytesIO(original)).is_encrypted)
        self.assertEqual(self.client.post(self.url(resource), {**self.payload(resource), 'cover': self.image()}).status_code, 302)
        resource.refresh_from_db()
        with resource.document.open("rb") as file:
            self.assertEqual(file.read(), original)
        replacement = SimpleUploadedFile("protected.pdf", original, content_type="application/pdf")
        response = self.client.post(self.url(resource), {**self.payload(resource), 'document': replacement})
        self.assertContains(response, '请先解除 PDF 密码保护')

    def test_direction_image_management_prefills_and_deletes(self):
        direction = ResearchDirection.objects.first()
        page = self.client.get(self.url(direction))
        self.assertContains(page, 'class="direction-image-manager"')
        self.assertContains(page, f'/manage/catalog/figure/add/?directions={direction.pk}')
        add = self.client.get(f'/manage/catalog/figure/add/?directions={direction.pk}')
        self.assertEqual(add.context['adminform'].form['directions'].value(), [str(direction.pk)])
        data = {"kind": "schematic", "title": "团队提供测试图片", "alt": "测试图片", "position": 0,
                "is_published": "on", "directions": [direction.pk], "image": self.image()}
        self.assertEqual(self.client.post('/manage/catalog/figure/add/', data).status_code, 302)
        figure = Figure.objects.get(title=data['title'])
        self.assertContains(self.client.get(self.url(direction)), self.url(figure, "delete"))
        self.assertContains(self.client.get('/research.html'), figure.image.url)
        self.assertContains(self.client.get('/' + direction.page_name), figure.image.url)
        form = self.client.get(self.url(figure))
        self.assertNotContains(form, 'name="image-clear"')
        self.assertEqual(self.client.post(self.url(figure), {**self.payload(figure), 'image': self.image()}).status_code, 302)
        figure.refresh_from_db()
        # Unlink one direction without deleting the shared image record.
        self.assertEqual(self.client.post(self.url(figure), {**self.payload(figure), 'directions': []}).status_code, 302)
        self.assertNotContains(self.client.get('/' + direction.page_name), figure.image.url)
        self.assertContains(self.client.get('/manage/catalog/figure/'), '未关联公开方向')
        self.assertContains(self.client.get(self.url(figure, 'delete')), '删除')
        self.assertEqual(self.client.post(self.url(figure, 'delete'), {'post': 'yes'}).status_code, 302)
        self.assertFalse(Figure.objects.filter(pk=figure.pk).exists())

    def test_optional_image_controls_work_without_javascript_and_escape_values(self):
        member = Member.objects.exclude(photo="").first()
        html = self.client.get(self.url(member)).content.decode()
        self.assertIn(f'src="{member.photo.url}"', html)
        self.assertIn('name="photo-clear"', html)
        self.assertIn('type="file" name="photo"', html)
        direction = ResearchDirection.objects.first()
        figure = direction.figures.first()
        figure.title = '<script>alert("x")</script>'
        figure.save()
        self.assertContains(self.client.get(self.url(direction)), '&lt;script&gt;')
        self.assertNotContains(self.client.get(self.url(direction)), '<script>alert("x")</script>')
