from django.db import models
from django.core.validators import MaxValueValidator, MinValueValidator
from .validators import upload_path, validate_image, validate_pdf, validate_web_url, pdf_metadata


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
    ROUTES = [("index", "首页"), ("research", "研究方向"), ("publications", "研究成果"),
              ("team", "研究团队"), ("resources", "学习资料"), ("contact", "联系我们")]
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
    text = models.TextField("完整介绍")

    class Meta(OrderedContent.Meta):
        verbose_name = verbose_name_plural = "研究方向"

    def __str__(self):
        return self.title


class Project(OrderedContent):
    title = models.CharField("课题名称", max_length=500)
    program = models.CharField("项目类别", max_length=200)
    dates = models.CharField("项目周期", max_length=100)
    code = models.CharField("项目编号", max_length=100, blank=True)

    class Meta(OrderedContent.Meta):
        verbose_name = verbose_name_plural = "科研项目"

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
    kind = models.CharField("成果类型", max_length=20, choices=KINDS, default="paper")
    title = models.CharField("成果题目", max_length=1000)
    authors = models.TextField("作者或获奖人", blank=True)
    year = models.PositiveIntegerField("年份", validators=[MinValueValidator(1900), MaxValueValidator(2200)])
    journal = models.CharField("期刊或颁发机构", max_length=300, blank=True)
    citation = models.CharField("卷期、页码或编号", max_length=300, blank=True)
    url = models.URLField("原文链接", max_length=2000, blank=True, validators=[validate_web_url])
    summary = models.TextField("补充说明", blank=True)

    class Meta(OrderedContent.Meta):
        ordering = ["-year", "position", "pk"]
        verbose_name = verbose_name_plural = "论文与其他成果"

    def __str__(self):
        return self.title


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
