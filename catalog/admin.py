from django.contrib import admin, messages
from django.db.models import F
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html, format_html_join
from .forms import VersionedForm
from .models import (SiteSettings, Page, ResearchDirection, Project, Member, Publication, Resource,
                     Figure, PubMedCandidate, PubMedImportRun)
from .pubmed import ImportFailure, accept

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


class StableSlugMixin:
    """Slugs become read-only once set so published file names never change by accident."""

    def get_readonly_fields(self, request, obj=None):
        fields = tuple(super().get_readonly_fields(request, obj))
        return fields + ("slug",) if obj and obj.slug else fields


@admin.register(ResearchDirection)
class ResearchAdmin(StableSlugMixin, ContentAdmin):
    list_display = ("title", "slug", "position", "is_published", "updated_at")
    list_filter = ("is_published",)
    search_fields = ("title", "text", "summary")
    fieldsets = [
        ("研究方向", {"fields": ["title", "short_title", "slug", "summary", "text", "edit_version"]}),
        ("研究层次（首页研究布局）", {"fields": ["covers_pathogen", "covers_host", "covers_clinical", "covers_intervention"],
                              "description": "表示该方向覆盖的研究层次，用于首页研究布局，不表示因果关系。"}),
        ("展示设置", {"fields": ["position", "is_published", "updated_at"],
                  "description": "方向页配图在「研究配图」中选择展示的研究方向；关联课题和成果分别在课题和成果中设置。"}),
    ]


@admin.register(Project)
class ProjectAdmin(ContentAdmin):
    list_display = ("title", "program", "dates", "code", "is_published")
    list_filter = ("is_published", "directions")
    search_fields = ("title", "code")
    filter_horizontal = ("directions",)


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
class PublicationAdmin(StableSlugMixin, ContentAdmin):
    list_display = ("title", "kind", "year", "journal", "pmid", "is_featured", "is_published")
    list_filter = ("kind", "year", "is_published", "is_featured", "directions")
    search_fields = ("title", "authors", "journal", "pmid", "doi")
    filter_horizontal = ("directions",)
    readonly_fields = ("figure_list", "updated_at")
    fieldsets = [
        ("成果信息", {"fields": ["kind", "title", "authors", "year", "journal", "citation", "edit_version"]}),
        ("标识与链接", {"fields": ["pmid", "doi", "pmcid", "url", "slug"]}),
        ("中文概述与关联", {"fields": ["summary", "directions", "lab_role", "source_note"]}),
        ("配图", {"fields": ["figure_list"]}),
        ("展示设置", {"fields": ["is_featured", "position", "is_published", "updated_at"],
                  "description": "成果公开后才会出现在前台；取消公开时，其配图也会同时从前台撤下。"}),
    ]

    @admin.display(description="本成果配图")
    def figure_list(self, obj):
        if not obj or not obj.pk:
            return "保存成果后，可在「研究配图」中添加。"
        rows = format_html_join("", '<li><a href="{}">{} {}</a>（{}）</li>',
                                ((reverse("admin:catalog_figure_change", args=[f.pk]), f.label, f.title,
                                  "公开" if f.is_published else "草稿") for f in obj.figures.all()))
        add = reverse("admin:catalog_figure_add") + f"?publication={obj.pk}"
        return format_html('<ul>{}</ul><a href="{}">添加配图</a>', rows, add)


@admin.register(Figure)
class FigureAdmin(ContentAdmin):
    list_display = ("preview", "title", "label", "publication", "kind", "is_published", "front_status")
    list_display_links = ("preview", "title")
    list_filter = ("is_published", "kind", "directions")
    search_fields = ("title", "caption", "label", "publication__title", "credit")
    autocomplete_fields = ("publication",)
    filter_horizontal = ("directions",)
    readonly_fields = ("preview", "updated_at")
    actions = ("publish", "unpublish")
    fieldsets = [
        ("图片", {"fields": ["kind", "image", "static_asset", "preview", "edit_version"],
                "description": "上传 JPG/PNG/WebP 原图，或选择开发者内置的 SVG 示意图（二选一）。替换图片时直接上传新文件。"}),
        ("说明", {"fields": ["publication", "label", "title", "caption", "alt"]}),
        ("出处记录", {"fields": ["credit", "source_url", "license_note"]}),
        ("展示", {"fields": ["directions", "position", "is_published", "updated_at"],
                "description": "论文原图只有在所属成果公开时才会在前台出现。"}),
    ]

    @admin.display(description="预览")
    def preview(self, obj):
        if obj and (obj.image or obj.static_asset):
            return format_html('<img src="{}" alt="" style="max-height:72px;max-width:120px">', obj.src)
        return "—"

    @admin.display(description="前台状态")
    def front_status(self, obj):
        if obj.is_public:
            return "已显示"
        return "成果未公开" if obj.is_published else "草稿"

    @admin.action(description="公开选中的图片", permissions=["change"])
    def publish(self, request, queryset):
        queryset.update(is_published=True, version=F("version") + 1)

    @admin.action(description="取消公开选中的图片", permissions=["change"])
    def unpublish(self, request, queryset):
        queryset.update(is_published=False, version=F("version") + 1)


@admin.register(PubMedCandidate)
class CandidateAdmin(ContentAdmin):
    list_display = ("pmid", "short_title", "year", "journal", "identity_status", "decision", "has_conflict", "publication")
    list_filter = ("decision", "identity_status", "year")
    search_fields = ("pmid", "doi", "title", "authors")
    actions = ("accept_selected", "reject_selected")
    readonly_fields = ("pmid", "doi", "pmcid", "title", "authors", "journal", "year", "citation", "publication_types",
                       "abstract", "identity_status", "identity_evidence", "query", "retrieved_at", "decision",
                       "decided_by", "decided_at", "publication", "conflict", "upstream_changes", "updated_at")
    fieldsets = [
        ("审核", {"fields": ["decision", "decision_note", "decided_by", "decided_at", "publication", "conflict",
                           "upstream_changes", "edit_version"],
                "description": "在列表中勾选候选，使用「纳入为成果草稿」或「标记为不纳入」。纳入后的成果默认不公开。"}),
        ("身份核验", {"fields": ["identity_status", "identity_evidence"],
                  "description": "依据 PubMed 作者单位判断是否为本课题组曹彬；不会根据作者顺序判断通讯作者。"}),
        ("PubMed 记录", {"fields": ["pmid", "doi", "pmcid", "title", "authors", "journal", "year", "citation",
                                  "publication_types", "abstract", "query", "retrieved_at", "updated_at"]}),
    ]

    def has_add_permission(self, request):
        return False

    @admin.display(description="题目")
    def short_title(self, obj):
        return obj.title[:80]

    @admin.display(description="冲突", boolean=True)
    def has_conflict(self, obj):
        return bool(obj.conflict)

    def has_accept_permission(self, request):
        return request.user.has_perm("catalog.change_pubmedcandidate") and request.user.has_perm("catalog.add_publication")

    @admin.action(description="纳入为成果草稿（不公开）", permissions=["accept"])
    def accept_selected(self, request, queryset):
        done = 0
        for candidate in queryset:
            try:
                accept(candidate, request.user)
                done += 1
            except ImportFailure as exc:
                self.message_user(request, str(exc), messages.ERROR)
        if done:
            self.message_user(request, f"已纳入 {done} 条为成果草稿。请在「论文与其他成果」补充中文概述后公开。", messages.SUCCESS)

    @admin.action(description="标记为不纳入", permissions=["change"])
    def reject_selected(self, request, queryset):
        count = queryset.filter(publication__isnull=True).update(
            decision="rejected", decided_by=request.user, decided_at=timezone.now(), version=F("version") + 1)
        self.message_user(request, f"已标记 {count} 条为不纳入；已纳入成果的候选不受影响。")


@admin.register(PubMedImportRun)
class ImportRunAdmin(admin.ModelAdmin):
    list_display = ("started_at", "status", "found", "created", "updated", "short_query", "message")
    list_filter = ("status",)
    readonly_fields = [f.name for f in PubMedImportRun._meta.fields]

    @admin.display(description="检索式")
    def short_query(self, obj):
        return obj.query[:80]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False



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
