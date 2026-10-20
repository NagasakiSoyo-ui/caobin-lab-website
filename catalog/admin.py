from django.contrib import admin
from .forms import VersionedForm
from .models import SiteSettings, Page, ResearchDirection, Project, Member, Publication, Resource

admin.site.site_header = "课题组 · 内容管理"
admin.site.site_title = "网站管理台"
admin.site.index_title = "内容工作台"
admin.site.site_url = "/"


class ContentAdmin(admin.ModelAdmin):
    form = VersionedForm
    readonly_fields = ("updated_at",)
    list_per_page = 30
    save_on_top = True

    def save_model(self, request, obj, form, change):
        if change:
            obj.version += 1
        super().save_model(request, obj, form, change)


@admin.register(SiteSettings)
class SiteSettingsAdmin(ContentAdmin):
    fieldsets = [
        ("网站名称", {"fields": ["name", "subtitle", "edit_version"]}),
        ("首页首屏", {"fields": ["hero_title", "hero_english", "hero_intro", "hero_photo"]}),
        ("课题组负责人", {"fields": ["leader_name", "leader_english", "leader_role", "leader_photo", "leader_bio"]}),
        ("联系信息", {"fields": ["contact_name", "contact_email", "updated_at"]}),
    ]

    def has_add_permission(self, request):
        return not SiteSettings.objects.exists() and super().has_add_permission(request)

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        obj.pk = 1
        super().save_model(request, obj, form, change)


@admin.register(Page)
class PageAdmin(ContentAdmin):
    list_display = ("title", "english", "updated_at")
    readonly_fields = ("slug", "updated_at")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ResearchDirection)
class ResearchAdmin(ContentAdmin):
    list_display = ("title", "position", "is_published", "updated_at")
    list_filter = ("is_published",)
    search_fields = ("title", "text")


@admin.register(Project)
class ProjectAdmin(ContentAdmin):
    list_display = ("title", "program", "dates", "is_published")
    list_filter = ("is_published",)
    search_fields = ("title", "code")


@admin.register(Member)
class MemberAdmin(ContentAdmin):
    list_display = ("name", "group", "stage", "school", "position", "is_published")
    list_filter = ("group", "is_published")
    search_fields = ("name", "school", "workplace")
    fieldsets = [
        ("基本资料", {"fields": ["name", "group", "stage", "photo", "edit_version"]}),
        ("个人介绍", {"fields": ["school", "workplace", "cohort", "bio"]}),
        ("展示设置", {"fields": ["position", "is_published", "updated_at"]}),
    ]


@admin.register(Publication)
class PublicationAdmin(ContentAdmin):
    list_display = ("title", "kind", "year", "journal", "is_published")
    list_filter = ("kind", "year", "is_published")
    search_fields = ("title", "authors", "journal")


@admin.register(Resource)
class ResourceAdmin(ContentAdmin):
    list_display = ("title", "kind", "disease", "year", "is_published")
    list_filter = ("kind", "disease", "is_published")
    search_fields = ("title", "english", "journal")
    readonly_fields = ("pages", "file_bytes", "updated_at")
    fieldsets = [
        ("资料信息", {"fields": ["title", "english", "kind", "disease", "edit_version"]}),
        ("出版信息", {"fields": ["year", "version_label", "journal"]}),
        ("文件", {"fields": ["document", "cover", "pages", "file_bytes"]}),
        ("展示设置", {"fields": ["position", "is_published", "updated_at"]}),
    ]
