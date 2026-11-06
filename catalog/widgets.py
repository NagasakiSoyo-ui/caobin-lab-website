from django.contrib.admin.widgets import AdminFileWidget


class AdminImageWidget(AdminFileWidget):
    template_name = "catalog/widgets/image.html"
    clear_checkbox_label = "移除当前图片（保存后生效）"

    def __init__(self, attrs=None):
        super().__init__({"accept": "image/jpeg,image/png,image/webp", **(attrs or {})})

    class Media:
        js = ("admin-image-preview.js",)
