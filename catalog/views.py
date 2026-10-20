from pathlib import Path
from django.conf import settings
from django.contrib import admin
from django.contrib.auth.decorators import permission_required
from django.http import HttpResponse, FileResponse, Http404
from django.views.decorators.http import require_GET
from .presentation import render_website
from .exporting import website_archive


@require_GET
def public_page(request, slug="index"):
    response = HttpResponse(render_website(slug))
    response["Content-Security-Policy"] = "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
    return response


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
    response = FileResponse(file.open("rb"), content_type=content_type)
    response["X-Content-Type-Options"] = "nosniff"
    response["Content-Disposition"] = f'inline; filename="{file.name}"'
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
