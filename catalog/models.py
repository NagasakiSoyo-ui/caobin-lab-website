from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.core.validators import MaxValueValidator, MinValueValidator
from django.templatetags.static import static
from .identifiers import normalize_doi, normalize_pmid, unique_slug
from .validators import upload_path, validate_image, validate_pdf, validate_web_url, pdf_metadata

# Research layers used on the home layout and direction pages. They describe where a
# direction works (a coverage map), not a causal pathway between layers.
LAYERS = [("pathogen", "病原"), ("host", "宿主"), ("clinical", "临床"), ("intervention", "干预")]


class Versioned(models.Model):
    version = models.PositiveIntegerField("版本", default=1, editable=False)
    updated_at = models.DateTimeField("最后修改", auto_now=True)

    class Meta:
        abstract = True


class OrderedContent(Versioned):
    position = models.PositiveIntegerField("显示顺序", default=100, help_text="数字越小越靠前。")
    is_published = models.BooleanField("在网站公开", default=False, help_text="勾选后保存即在前台显示；取消勾选可保留草稿。")

    class Meta:
        abstract = True
        ordering = ["position", "pk"]


class SiteSettings(Versioned):
    name = models.CharField("课题组名称", max_length=100)
    subtitle = models.CharField("副标题", max_length=200)
    hero_title = models.CharField("首页主标题", max_length=200)
    hero_english = models.CharField("首页英文标题", max_length=300, blank=True)
    hero_intro = models.TextField("首页简介")
    hero_photo = models.ImageField("首页大图", upload_to=upload_path, validators=[validate_image], blank=True)
    leader_name = models.CharField("负责人姓名", max_length=100)
    leader_english = models.CharField("负责人英文名", max_length=100, blank=True)
    leader_role = models.CharField("负责人职务", max_length=200)
    leader_bio = models.TextField("负责人完整介绍", help_text="段落之间空一行，不需要输入 HTML。")
    leader_photo = models.ImageField("负责人照片", upload_to=upload_path, validators=[validate_image], blank=True)
    contact_name = models.CharField("联系人", max_length=100)
    contact_email = models.EmailField("联系邮箱")

    class Meta:
        verbose_name = verbose_name_plural = "网站与负责人设置"
        constraints = [models.CheckConstraint(condition=models.Q(pk=1), name="single_site_settings")]

    def __str__(self):
        return self.name


class Page(Versioned):
    ROUTES = [("index", "首页"), ("research", "研究方向"), ("projects", "科研课题"), ("publications", "研究成果"),
              ("team", "研究团队"), ("resources", "学习资料"), ("contact", "联系与加入")]
    slug = models.CharField("栏目", max_length=20, choices=ROUTES, unique=True)
    title = models.CharField("栏目名称", max_length=50)
    english = models.CharField("英文名称", max_length=100, blank=True)
    intro = models.TextField("栏目简介", blank=True)

    class Meta:
        verbose_name = verbose_name_plural = "栏目文字"
        ordering = ["pk"]

    def __str__(self):
        return self.title


class ResearchDirection(OrderedContent):
    title = models.CharField("研究方向", max_length=300)
    short_title = models.CharField("简称", max_length=30, blank=True, help_text="用于首页研究布局图，建议 10 字以内；留空则截取标题。")
    slug = models.SlugField("链接名", max_length=80, unique=True, blank=True,
                            help_text="详情页文件名 research-链接名.html。首次保存后固定，修改会使外部旧链接失效。")
    summary = models.TextField("中文简介", blank=True, help_text="列表卡片与详情页开头显示的简介；完整介绍另行保留。")
    text = models.TextField("完整介绍")
    covers_pathogen = models.BooleanField("研究层次：病原", default=False)
    covers_host = models.BooleanField("研究层次：宿主", default=False)
    covers_clinical = models.BooleanField("研究层次：临床", default=False)
    covers_intervention = models.BooleanField("研究层次：干预", default=False)

    class Meta(OrderedContent.Meta):
        verbose_name = verbose_name_plural = "研究方向"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug(ResearchDirection, self.short_title or self.title or "direction", self.pk)
            if not any(ch.isalpha() for ch in self.slug) or self.slug == "item":
                self.slug = unique_slug(ResearchDirection, "direction", self.pk)
        super().save(*args, **kwargs)

    @property
    def page_name(self):
        return direction_filename(self.slug)

    @property
    def label(self):
        return self.short_title or (self.title if len(self.title) <= 12 else self.title[:11] + "…")

    @property
    def layers(self):
        return [(key, name) for key, name in LAYERS if getattr(self, f"covers_{key}")]

    def __str__(self):
        return self.title


class Project(OrderedContent):
    title = models.CharField("课题名称", max_length=500)
    program = models.CharField("项目类别", max_length=200)
    dates = models.CharField("项目周期", max_length=100)
    code = models.CharField("项目编号", max_length=100, blank=True)
    directions = models.ManyToManyField(ResearchDirection, verbose_name="关联研究方向", blank=True, related_name="projects")

    class Meta(OrderedContent.Meta):
        verbose_name = verbose_name_plural = "科研课题"

    def __str__(self):
        return self.title


class Member(OrderedContent):
    GROUPS = [("faculty", "团队骨干"), ("postdocs", "博士后"), ("students", "在读研究生"), ("alumni", "已毕业成员")]
    name = models.CharField("姓名", max_length=100)
    group = models.CharField("所属分组", max_length=20, choices=GROUPS)
    stage = models.CharField("职务或学习阶段", max_length=100, blank=True)
    school = models.CharField("学校", max_length=200, blank=True)
    workplace = models.CharField("工作单位", max_length=300, blank=True)
    cohort = models.CharField("入学年级", max_length=100, blank=True)
    bio = models.TextField("个人介绍", blank=True)
    photo = models.ImageField("成员照片", upload_to=upload_path, validators=[validate_image], blank=True)

    class Meta(OrderedContent.Meta):
        verbose_name = verbose_name_plural = "团队成员"

    def __str__(self):
        return f"{self.name} · {self.get_group_display()}"


class Publication(OrderedContent):
    KINDS = [("paper", "研究论文"), ("award", "奖项"), ("patent", "专利"), ("book", "著作"), ("guideline", "指南与共识")]
    ROLES = [("unverified", "未标注"), ("lead", "课题组牵头或通讯"), ("participant", "课题组参与")]
    kind = models.CharField("成果类型", max_length=20, choices=KINDS, default="paper")
    title = models.CharField("成果题目", max_length=1000)
    authors = models.TextField("作者或获奖人", blank=True)
    year = models.PositiveIntegerField("年份", validators=[MinValueValidator(1900), MaxValueValidator(2200)])
    journal = models.CharField("期刊或颁发机构", max_length=300, blank=True)
    citation = models.CharField("卷期、页码或编号", max_length=300, blank=True)
    url = models.URLField("原文链接", max_length=2000, blank=True, validators=[validate_web_url])
    summary = models.TextField("中文概述", blank=True, help_text="人工撰写的中文概述；PubMed 导入和初始化不会覆盖已有内容。")
    pmid = models.CharField("PMID", max_length=12, unique=True, null=True, blank=True)
    doi = models.CharField("DOI", max_length=200, unique=True, null=True, blank=True, help_text="保存时自动去掉 https://doi.org/ 前缀并转为小写。")
    pmcid = models.CharField("PMCID", max_length=20, blank=True)
    slug = models.SlugField("链接名", max_length=80, unique=True, null=True, blank=True,
                            help_text="详情页文件名 publication-链接名.html。首次保存后固定。")
    is_featured = models.BooleanField("精选并生成详情页", default=False, help_text="精选成果在研究成果页图文展示，并生成固定详情页。")
    lab_role = models.CharField("课题组角色", max_length=20, choices=ROLES, default="unverified", blank=True,
                                help_text="不按作者顺序自动判断；请依据原文通讯作者标注人工选择。")
    directions = models.ManyToManyField(ResearchDirection, verbose_name="关联研究方向", blank=True, related_name="publications")
    source_note = models.TextField("来源与身份核验记录", blank=True, help_text="检索来源、时间、作者单位等核验依据。")

    class Meta(OrderedContent.Meta):
        ordering = ["-year", "position", "pk"]
        verbose_name = verbose_name_plural = "论文与其他成果"

    def clean(self):
        super().clean()
        try:
            self.pmid = normalize_pmid(self.pmid)
        except ValueError as exc:
            raise ValidationError({"pmid": str(exc)})
        self.doi = normalize_doi(self.doi)

    def save(self, *args, **kwargs):
        self.pmid = normalize_pmid(self.pmid)
        self.doi = normalize_doi(self.doi)
        self.lab_role = self.lab_role or "unverified"
        if not self.slug:
            words = " ".join(self.title.split()[:6])
            self.slug = unique_slug(Publication, f"{self.year} {words}", self.pk)
        super().save(*args, **kwargs)

    @property
    def page_name(self):
        return publication_filename(self.slug)

    @property
    def has_detail(self):
        return self.is_published and self.is_featured and bool(self.slug)

    @property
    def pubmed_url(self):
        return f"https://pubmed.ncbi.nlm.nih.gov/{self.pmid}/" if self.pmid else ""

    @property
    def doi_url(self):
        return f"https://doi.org/{self.doi}" if self.doi else ""

    @property
    def pmc_url(self):
        return f"https://pmc.ncbi.nlm.nih.gov/articles/{self.pmcid}/" if self.pmcid else ""

    @property
    def authors_short(self):
        names = [name.strip() for name in self.authors.split(",") if name.strip()]
        if len(names) <= 6:
            return ", ".join(names)
        return ", ".join(names[:3]) + ", …, " + names[-1]

    def __str__(self):
        return self.title


def direction_filename(slug):
    return f"research-{slug}.html"


def publication_filename(slug):
    return f"publication-{slug}.html"


# Developer-maintained SVG schematics in static/site/figures/. Administrators can only pick
# from this list; uploading SVG through the admin is intentionally not supported.
STATIC_FIGURES = [
    ("direction-translation.svg", "临床转化方向：研究布局示意"),
]


class Figure(Versioned):
    KINDS = [("original", "论文原图"), ("schematic", "原创示意图")]
    kind = models.CharField("图片类型", max_length=20, choices=KINDS, default="original")
    publication = models.ForeignKey(Publication, verbose_name="所属成果", null=True, blank=True,
                                    on_delete=models.CASCADE, related_name="figures",
                                    help_text="论文原图须选择所属成果；成果取消公开时，图片随之在前台撤下。")
    directions = models.ManyToManyField(ResearchDirection, verbose_name="在研究方向页展示", blank=True, related_name="figures")
    label = models.CharField("原文图号", max_length=50, blank=True, help_text="例如 Fig. 6；示意图可留空。")
    title = models.CharField("图题", max_length=300)
    caption = models.TextField("中文图片说明", help_text="说明图中展示的内容，忠实原文图义，不扩展结论。")
    alt = models.CharField("替代文字", max_length=300, help_text="供读屏软件使用的简短描述。")
    image = models.ImageField("图片文件", upload_to=upload_path, validators=[validate_image], blank=True,
                              help_text="JPG、PNG 或 WebP；替换图片即上传新文件。")
    static_asset = models.CharField("内置示意图", max_length=100, choices=STATIC_FIGURES, blank=True,
                                    help_text="开发者维护的 SVG 示意图，与上传图片二选一。")
    credit = models.CharField("作者与出处", max_length=500, blank=True, help_text="例如：Zou X, et al. Signal Transduct Target Ther. 2025.")
    source_url = models.URLField("原图来源链接", max_length=2000, blank=True, validators=[validate_web_url])
    license_note = models.CharField("使用说明", max_length=300, blank=True, help_text="原文许可或使用依据，例如 CC BY 4.0、课题组自有论文。")
    position = models.PositiveIntegerField("显示顺序", default=100)
    is_published = models.BooleanField("在网站公开", default=False)

    class Meta:
        ordering = ["position", "pk"]
        verbose_name = verbose_name_plural = "研究配图"

    def clean(self):
        super().clean()
        if bool(self.image) == bool(self.static_asset):
            raise ValidationError("请上传图片文件或选择一个内置示意图（二选一）。")
        if self.kind == "original" and not (self.publication_id and self.label and self.credit and self.source_url):
            raise ValidationError("论文原图需要填写所属成果、原文图号、作者与出处和原图来源链接。")

    @property
    def src(self):
        return self.image.url if self.image else static(f"site/figures/{self.static_asset}")

    @property
    def is_public(self):
        return self.is_published and (self.publication is None or self.publication.is_published)

    def __str__(self):
        return f"{self.label} {self.title}".strip()


class PubMedImportRun(models.Model):
    STATUSES = [("ok", "成功"), ("empty", "无结果"), ("failed", "失败")]
    started_at = models.DateTimeField("开始时间", auto_now_add=True)
    finished_at = models.DateTimeField("结束时间", null=True, blank=True)
    query = models.TextField("检索式或 PMID")
    status = models.CharField("结果", max_length=10, choices=STATUSES, default="failed")
    found = models.PositiveIntegerField("记录数", default=0)
    created = models.PositiveIntegerField("新增候选", default=0)
    updated = models.PositiveIntegerField("刷新候选", default=0)
    message = models.TextField("说明", blank=True)

    class Meta:
        ordering = ["-started_at"]
        verbose_name = verbose_name_plural = "PubMed 导入记录"

    def __str__(self):
        return f"{self.started_at:%Y-%m-%d %H:%M} · {self.get_status_display()}"


class PubMedCandidate(Versioned):
    DECISIONS = [("pending", "待审核"), ("accepted", "已纳入成果"), ("rejected", "不纳入")]
    IDENTITY = [("matched", "单位匹配"), ("unmatched", "单位未匹配，需人工核实")]
    pmid = models.CharField("PMID", max_length=12, unique=True)
    doi = models.CharField("DOI", max_length=200, blank=True)
    pmcid = models.CharField("PMCID", max_length=20, blank=True)
    title = models.TextField("题目")
    authors = models.TextField("作者", blank=True)
    journal = models.CharField("期刊", max_length=300, blank=True)
    year = models.PositiveIntegerField("年份", null=True, blank=True)
    citation = models.CharField("卷期页码", max_length=300, blank=True)
    abstract = models.TextField("英文摘要", blank=True)
    publication_types = models.CharField("文献类型", max_length=500, blank=True)
    identity_status = models.CharField("身份判断", max_length=20, choices=IDENTITY, default="unmatched")
    identity_evidence = models.TextField("身份判断依据", blank=True)
    query = models.TextField("检索来源", blank=True)
    retrieved_at = models.DateTimeField("最近检索时间")
    decision = models.CharField("审核决定", max_length=20, choices=DECISIONS, default="pending")
    decision_note = models.TextField("审核备注", blank=True)
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="审核人", null=True, blank=True,
                                   on_delete=models.SET_NULL, related_name="+")
    decided_at = models.DateTimeField("审核时间", null=True, blank=True)
    publication = models.ForeignKey(Publication, verbose_name="对应成果", null=True, blank=True,
                                    on_delete=models.SET_NULL, related_name="candidates")
    conflict = models.TextField("冲突提示", blank=True)
    upstream_changes = models.TextField("PubMed 新变化", blank=True,
                                        help_text="已纳入成果后 PubMed 记录发生的变化，仅提示，不自动写回成果。")

    class Meta:
        ordering = ["-year", "-pmid"]
        verbose_name = verbose_name_plural = "PubMed 候选"

    def __str__(self):
        return f"PMID {self.pmid} · {self.title[:60]}"


class Resource(OrderedContent):
    title = models.CharField("资料标题", max_length=500)
    english = models.CharField("英文标题", max_length=700, blank=True)
    kind = models.CharField("资料类型", max_length=50, help_text="例如：指南、专家共识、指南摘要。")
    disease = models.CharField("疾病方向", max_length=100)
    year = models.PositiveIntegerField("发表年份", validators=[MinValueValidator(1900), MaxValueValidator(2200)])
    version_label = models.CharField("版本说明", max_length=200, blank=True, help_text="例如：2025版 · 2026年刊出。")
    journal = models.CharField("来源或期刊", max_length=200, blank=True)
    document = models.FileField("PDF 原文", upload_to=upload_path, validators=[validate_pdf])
    cover = models.ImageField("封面图片", upload_to=upload_path, validators=[validate_image], blank=True)
    pages = models.PositiveIntegerField("页数", default=0, editable=False)
    file_bytes = models.PositiveIntegerField("文件大小", default=0, editable=False)

    class Meta(OrderedContent.Meta):
        ordering = ["-year", "position", "pk"]
        verbose_name = verbose_name_plural = "学习资料"

    def save(self, *args, **kwargs):
        if self.document and (not self.document._committed or not self.pages):
            self.pages, self.file_bytes = pdf_metadata(self.document)
        super().save(*args, **kwargs)

    @property
    def megabytes(self):
        return self.file_bytes / (1024 * 1024)

    def __str__(self):
        return self.title
