from django.contrib import admin
from django.urls import path
from catalog import views
from catalog.models import Page

urlpatterns = [
    path("", views.public_page),
    path("robots.txt", views.robots),
    path("media/<path:filename>", views.media_file),
    path("manage/export/", views.export_site, name="export_site"),
    path("manage/", admin.site.urls),
] + [path(f"{slug}.html", views.public_page, {"slug": slug}, name=slug) for slug, _ in Page.ROUTES]
