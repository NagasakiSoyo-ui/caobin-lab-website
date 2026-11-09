from django import forms
from django.contrib import admin, messages
from django.db import transaction
from django.db.models import ImageField
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.html import format_html_join
from urllib.parse import urlsplit
from .forms import VersionedForm
from .widgets import AdminImageWidget
from .models import (SiteSettings, HomeSlide, Page, ResearchDirection, Project, Member, Publication, Resource,
                     Figure, PubMedCandidate, PubMedImportRun, News)
from .pubmed import ImportFailure, accept, reset_to_pending
from .presentation import public_home_slides

admin.site.site_header = "后台管理"
admin.site.site_title = "后台管理"
admin.site.index_title = "后台管理"
admin.site.site_url = "/"


class ContentAdmin(admin.ModelAdmin):
    change_form_template = "admin/catalog/change_form.html"
    form = VersionedForm
    readonly_fields = ("updated_at",)
    list_per_page = 30
    save_on_top = True
    formfield_overrides = {ImageField: {"widget": AdminImageWidget}}

    def render_change_form(self, request, context, *args, **kwargs):
        obj = context.get("original")
        page = None
        if obj:
            if isinstance(obj, Page):
                page = reverse(obj.slug)
            elif isinstance(obj, ResearchDirection):
                page = reverse("direction", args=[obj.slug]) if obj.is_published else reverse("research")
            elif isinstance(obj, Figure):
                direction = obj.directions.filter(is_published=True).first() if obj.is_public else None
                if direction:
                    page = reverse("direction", args=[direction.slug]) + f"#figure-{obj.pk}"
            else:
                route = {SiteSettings: "index", HomeSlide: "index", Member: "team", Project: "projects",
                         Publication: "publications", Resource: "resources", News: "news"}.get(type(obj))
                if route:
                    page = reverse(route)
        context["saved_page_url"] = page
        return super().render_change_form(request, context, *args, **kwargs)

    def render_figure_manager(self, obj, relation):
        return render_to_string("admin/catalog/figure_manager.html", {
            "figures": obj.figures.select_related("publication").prefetch_related("directions"),
            "add_url": reverse("admin:catalog_figure_add") + f"?{relation}={obj.pk}",
        })

    def save_model(self, request, obj, form, change):
        if change:
            obj.version += 1
        super().save_model(request, obj, form, change)

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        # A plain checkbox list shows every research direction (published or not) with its full title.
        if db_field.name == "directions":
            kwargs["widget"] = forms.CheckboxSelectMultiple
        return super().formfield_for_manytomany(db_field, request, **kwargs)


@admin.register(SiteSettings)
class SiteSettingsAdmin(ContentAdmin):
    fieldsets = [
        ("网站名称", {"fields": ["name", "subtitle", "edit_version"]}),
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


@admin.register(News)
class NewsAdmin(ContentAdmin):
    list_display = ("title", "published_on", "position", "is_published", "updated_at")
    list_filter = ("is_published", "published_on")
    search_fields = ("title", "text")
    fieldsets = [
        ("动态内容", {"fields": ["title", "published_on", "text", "photo", "source_url", "edit_version"]}),
        ("展示设置", {"fields": ["position", "is_published", "updated_at"]}),
    ]


@admin.register(HomeSlide)
class HomeSlideAdmin(ContentAdmin):
    list_display = ("title", "position", "is_published", "front_status", "updated_at")
    list_select_related = ("source_direction", "source_figure__publication")
    readonly_fields = ("front_status", "updated_at")
    list_filter = ("is_published",)
    search_fields = ("title", "intro")
    fieldsets = [
        ("轮播内容", {"fields": ["title", "english", "intro", "photo", "image_fit", "edit_version"]}),
        ("来源关联", {"fields": ["source_direction", "source_figure"], "classes": ["collapse"]}),
        ("展示设置", {"fields": ["position", "is_published", "front_status", "updated_at"],
                    "description": "数字越小越靠前。取消公开可暂时撤下；全部撤下时首页不显示轮播。"}),
    ]

    @admin.display(description="前台状态")
    def front_status(self, obj):
        if not obj or not obj.pk:
            return "保存后显示"
        if not obj.is_published:
            return "草稿"
        if public_home_slides().filter(pk=obj.pk).exists():
            return "已显示"
        if obj.source_direction and not obj.source_direction.is_published:
            return "来源研究方向未公开，未展示"
        if obj.source_figure and not obj.source_figure.is_published:
            return "来源配图未公开，未展示"
        return "来源配图所属成果未公开，未展示"


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
    readonly_fields = ("figure_list", "updated_at")
    fieldsets = [
        ("研究方向", {"fields": ["title", "short_title", "slug", "summary", "text", "edit_version"]}),
        ("配图管理", {"fields": ["figure_list"],
                    "description": "可添加多张图片；显示顺序数字越小越靠前，第一张公开图片作为方向列表封面。"}),
        ("研究层次（首页研究布局）", {"fields": ["covers_pathogen", "covers_host", "covers_clinical", "covers_intervention"],
                              "description": "表示该方向覆盖的研究层次，用于首页研究布局，不表示因果关系。"}),
        ("展示设置", {"fields": ["position", "is_published", "updated_at"],
                  "description": "关联课题和成果分别在课题和成果中设置。"}),
    ]

    @admin.display(description="本方向图片")
    def figure_list(self, obj):
        if not obj or not obj.pk:
            return "先保存研究方向，再添加图片。"
        return self.render_figure_manager(obj, "directions")


@admin.register(Project)
class ProjectAdmin(ContentAdmin):
    list_display = ("title", "program", "dates", "code", "is_published")
    list_filter = ("is_published", "directions")
    search_fields = ("title", "code")
    fieldsets = [
        ("课题信息", {"fields": ["title", "program", "dates", "code", "edit_version"]}),
        ("展示设置", {"fields": ["directions", "position", "is_published", "updated_at"]}),
    ]


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
    list_display = ("title", "kind", "year", "journal", "pmid", "is_published")
    list_filter = ("kind", "year", "is_published", "directions")
    search_fields = ("title", "authors", "journal", "pmid", "doi", "registration_number")
    readonly_fields = ("figure_list", "updated_at")
    fieldsets = [
        ("成果信息", {"fields": ["kind", "title", "authors", "year", "journal", "citation", "edit_version"]}),
        ("标识与链接", {"fields": ["pmid", "doi", "pmcid", "url", "document", "slug"]}),
        ("专利与软件著作权", {"fields": ["registration_number", "registered_on"],
                         "description": "填写核实后的专利号或登记号及日期；研究论文无需填写。"}),
        ("中文概述与关联", {"fields": ["summary", "directions", "lab_role", "source_note"]}),
        ("配图", {"fields": ["figure_list"]}),
        ("展示设置", {"fields": ["position", "is_published", "updated_at"],
                  "description": "成果公开后才会出现在前台；取消公开时，其配图也会同时从前台撤下。"}),
    ]

    @admin.display(description="本成果配图")
    def figure_list(self, obj):
        if not obj or not obj.pk:
            return "保存成果后，可在「研究配图」中添加。"
        return self.render_figure_manager(obj, "publication")


@admin.register(Figure)
class FigureAdmin(ContentAdmin):
    delete_confirmation_template = "admin/catalog/figure_delete.html"
    delete_selected_confirmation_template = "admin/catalog/figure_delete_selected.html"
    list_display = ("preview", "title", "label", "publication", "kind", "is_published", "front_status")
    list_display_links = ("preview", "title")
    list_filter = ("is_published", "kind", "directions")
    search_fields = ("title", "caption", "label", "publication__title", "credit")
    autocomplete_fields = ("publication",)
    readonly_fields = ("updated_at",)
    actions = ("publish", "unpublish")
    fieldsets = [
        ("图片", {"fields": ["kind", "image", "edit_version"],
                "description": "上传团队提供或有原始出处的 JPG/PNG/WebP 图片，不使用 AI 生成图片。"}),
        ("说明", {"fields": ["publication", "label", "title", "caption", "alt"]}),
        ("出处记录", {"fields": ["credit", "source_url", "license_note"]}),
        ("展示", {"fields": ["directions", "position", "is_published", "updated_at"],
                "description": "选择展示方向并勾选公开后，图片才会出现在对应方向页。论文原图还需要所属成果已公开。删除整张配图请使用页面底部的“删除”；只从某方向撤下，取消该方向的勾选后保存。"}),
    ]

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name == "image":
            # A figure is an image record, unlike an optional member photo or cover.
            # Clearing its only file cannot produce a valid figure; delete the record instead.
            kwargs["required"] = True
        return super().formfield_for_dbfield(db_field, request, **kwargs)

    @admin.display(description="预览")
    def preview(self, obj):
        if obj and obj.image:
            return format_html('<img src="{}" alt="" style="max-height:72px;max-width:120px">', obj.src)
        return "—"

    @admin.display(description="前台状态")
    def front_status(self, obj):
        if not obj.is_published:
            return "草稿"
        if not obj.is_public:
            return "所属成果未公开"
        if not obj.directions.filter(is_published=True).exists():
            return "未关联公开方向"
        return "已显示"

    def _set_published(self, request, queryset, value, label):
        # Save each figure like an ordinary edit: bumps version, refreshes updated_at, writes the admin log.
        changed = 0
        for figure in queryset.select_for_update():
            if figure.is_published == value:
                continue
            figure.is_published = value
            figure.version += 1
            figure.save(update_fields=["is_published", "version", "updated_at"])
            self.log_change(request, figure, f"批量{label}（在网站公开）")
            changed += 1
        self.message_user(request, f"已{label} {changed} 张图片。")

    @admin.action(description="公开选中的图片", permissions=["change"])
    def publish(self, request, queryset):
        with transaction.atomic():
            self._set_published(request, queryset, True, "公开")

    @admin.action(description="取消公开选中的图片", permissions=["change"])
    def unpublish(self, request, queryset):
        with transaction.atomic():
            self._set_published(request, queryset, False, "取消公开")


@admin.register(PubMedCandidate)
class CandidateAdmin(ContentAdmin):
    list_display = ("pmid", "short_title", "year", "journal", "identity_status", "decision", "has_conflict", "publication")
    list_filter = ("decision", "identity_status", "year")
    search_fields = ("pmid", "doi", "title", "authors")
    actions = ("accept_selected", "reject_selected", "reset_selected")
    readonly_fields = ("pmid", "doi", "pmcid", "title", "authors", "journal", "year", "citation", "publication_types",
                       "abstract", "identity_status", "identity_evidence", "query", "retrieved_at", "decision",
                       "decided_by", "decided_at", "publication", "conflict", "upstream_changes", "updated_at")

    def get_readonly_fields(self, request, obj=None):
        # PubMed sometimes has no publication year; let an editor enter the verified year instead of guessing.
        fields = super().get_readonly_fields(request, obj)
        if obj and obj.year is None and not obj.publication_id:
            return tuple(f for f in fields if f != "year")
        return fields
    fieldsets = [
        ("审核", {"fields": ["decision", "decision_note", "decided_by", "decided_at", "publication", "conflict",
                           "upstream_changes", "edit_version"],
                "description": "在列表中勾选候选，使用「纳入为成果草稿」或「标记为不纳入」。纳入后的成果默认不公开。"}),
        ("身份核验", {"fields": ["identity_status", "identity_evidence"],
                  "description": "依据 PubMed 作者单位判断是否为本课题组曹彬；不会根据作者顺序判断通讯作者。"}),
        ("PubMed 记录", {"description": "年份缺失时可在此填写经原文核对的年份（保存会记入操作记录），否则无法纳入。",
                        "fields": ["pmid", "doi", "pmcid", "title", "authors", "journal", "year", "citation",
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
                publication = accept(candidate, request.user)
                done += 1
                self.log_change(request, candidate, f"纳入为成果草稿 #{publication.pk}")
            except ImportFailure as exc:
                self.message_user(request, str(exc), messages.ERROR)
        if done:
            self.message_user(request, f"已纳入 {done} 条为成果草稿。请在「论文与其他成果」核对原始内容后公开。", messages.SUCCESS)

    @admin.action(description="标记为不纳入", permissions=["change"])
    def reject_selected(self, request, queryset):
        count = 0
        with transaction.atomic():
            for candidate in queryset.select_for_update().filter(publication__isnull=True).exclude(decision="rejected"):
                candidate.decision, candidate.decided_by, candidate.decided_at = "rejected", request.user, timezone.now()
                candidate.version += 1
                candidate.save()
                self.log_change(request, candidate, "标记为不纳入")
                count += 1
        self.message_user(request, f"已标记 {count} 条为不纳入；已纳入成果的候选不受影响。")

    @admin.action(description="恢复为待审核（撤销「不纳入」）", permissions=["change"])
    def reset_selected(self, request, queryset):
        count = 0
        for candidate in queryset:
            if reset_to_pending(candidate, request.user):
                self.log_change(request, candidate, "将「不纳入」恢复为待审核")
                count += 1
        skipped = queryset.count() - count
        self.message_user(request, f"已恢复 {count} 条为待审核。" + (f"{skipped} 条不是「不纳入」状态或已关联成果，未改动。" if skipped else ""))


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
    list_display = ("title", "kind", "disease", "year", "position", "is_published")
    list_filter = ("kind", "disease", "is_published")
    search_fields = ("title", "english", "journal", "authors")
    readonly_fields = ("pages", "file_bytes", "display_category", "updated_at")
    fieldsets = [
        ("资料信息", {"fields": ["title", "english", "kind", "display_category", "disease", "edit_version"]}),
        ("出版信息", {"fields": ["year", "published_on", "authors", "version_label", "journal"]}),
        ("文件与链接", {"fields": ["document", "source_url", "cover", "pages", "file_bytes"]}),
        ("展示设置", {"fields": ["position", "is_published", "updated_at"]}),
    ]

    @admin.display(description="前台分类")
    def display_category(self, obj):
        return obj.category if obj and obj.kind else "选择资料类型并保存后显示。"

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name == "kind":
            # Existing editorial types remain distinct. The form prevents accidental new
            # spellings without reclassifying imported records or maintaining a second enum.
            kinds = Resource.objects.order_by('kind').values_list('kind', flat=True).distinct()
            return forms.ChoiceField(label=db_field.verbose_name,
                                     choices=[('', '---------')] + [(kind, kind) for kind in kinds],
                                     help_text="选择已有资料类型，避免同一类型因不同写法形成重复分类。")
        return super().formfield_for_dbfield(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not obj.source_url or 'source_url' not in form.changed_data:
            return

        def comparison_key(value):
            url = urlsplit(value)
            return url.netloc.casefold(), url.path.rstrip('/'), url.query

        # Different schemes/trailing slashes can be different resources. Flag candidates
        # for the editor; never rewrite their original URLs or silently merge records.
        key = comparison_key(obj.source_url)
        candidates = Resource.objects.exclude(pk=obj.pk).filter(source_url__icontains=key[0])
        similar = [item for item in candidates if comparison_key(item.source_url) == key][:5]
        if similar:
            links = format_html_join('；', '<a href="{}">{}</a>',
                                     ((reverse('admin:catalog_resource_change', args=[item.pk]), item.title)
                                      for item in similar))
            self.message_user(request, format_html('已保存。以下资料的链接可能指向相同内容，请核对（原链接未修改）：{}', links),
                              level=messages.WARNING)
