from django import forms


class VersionedForm(forms.ModelForm):
    edit_version = forms.IntegerField(widget=forms.HiddenInput, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["edit_version"].initial = self.instance.version

    def clean(self):
        values = super().clean()
        if self.instance.pk:
            current = type(self.instance).objects.filter(pk=self.instance.pk).values_list("version", flat=True).first()
            if current != values.get("edit_version"):
                raise forms.ValidationError("这条内容已被另一个窗口修改或删除。请先另开页面查看最新内容，再重新编辑；本次没有覆盖他人的修改。")
        return values
