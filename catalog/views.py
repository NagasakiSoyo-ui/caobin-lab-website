from pathlib import Path
from django.conf import settings
from django.contrib import admin
from django.contrib.auth.decorators import permission_required
from django.http import HttpResponse, FileResponse, Http404
from django.views.decorators.http import require_GET
from .models import Resource, Publication, SiteSettings, Member, HomeSlide, Figure, News
from .presentation import render_website, render_direction, public_figures, public_home_slides
from .exporting import website_archive

CSP = "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"


def _public(html):
    if html is None:
        raise Http404
    response = HttpResponse(html)
    response["Content-Security-Policy"] = CSP
    return response


@require_GET
def public_page(request, slug="index"):
    return _public(render_website(slug))


@require_GET
def direction_page(request, slug):
    return _public(render_direction(slug))


@require_GET
def media_file(request, filename):
    root = Path(settings.MEDIA_ROOT).resolve()
    file = (root / filename).resolve()
    if not file.is_relative_to(root) or not file.is_file():
        raise Http404
    types = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp", ".pdf": "application/pdf"}
    content_type = types.get(file.suffix.lower())
    if not content_type:
        raise Http404
    # Browsers let the response's Content-Disposition file name override <a download>, so a published
    # resource PDF is named after its title here too. It stays inline so "阅读原文" still opens in the browser.
    relative = file.relative_to(root).as_posix()
    references = [
        (Resource, 'document', Resource.objects.filter(is_published=True)),
        (Publication, 'document', Publication.objects.filter(is_published=True)),
        (Resource, 'cover', Resource.objects.filter(is_published=True)),
        (SiteSettings, 'leader_photo', SiteSettings.objects.all()),
        (Member, 'photo', Member.objects.filter(is_published=True)),
        (HomeSlide, 'photo', public_home_slides()),
        (News, 'photo', News.objects.filter(is_published=True)),
        (Figure, 'image', public_figures()),
    ]
    name, allowed = file.name, False
    for model, field, public in references:
        # Editors may preview draft files of models they can view. Removed/orphaned files
        # stay on disk for backups but are not an anonymous file server.
        query = model.objects.all() if request.user.is_active and request.user.is_staff and request.user.has_perm(
            f'catalog.view_{model._meta.model_name}') else public
        reference = query.filter(**{field: relative}).first()
        if reference:
            allowed = True
            if field == 'document':
                name = reference.download_name
            break
    if not allowed:
        raise Http404
    response = FileResponse(file.open("rb"), content_type=content_type, filename=name)
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, no-store"
    return response


@admin.site.admin_view
@permission_required("catalog.view_sitesettings", raise_exception=True)
@require_GET
def export_site(request):
    archive = website_archive()
    return FileResponse(archive, as_attachment=True, filename="caobin-lab-offline.zip", content_type="application/zip")


@require_GET
def robots(request):
    return HttpResponse("User-agent: *\nDisallow: /manage/\n", content_type="text/plain")
