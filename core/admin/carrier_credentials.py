from django import forms
from django.contrib import admin

from ..carrier_credentials_models import CarrierCredential, CarrierCredentialLog


class CarrierCredentialForm(forms.ModelForm):
    new_password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(render_value=False, attrs={"autocomplete": "new-password"}),
        help_text="Write-only. Leave empty to keep the saved password.",
    )

    class Meta:
        model = CarrierCredential
        exclude = ("password_enc", "consecutive_failures", "last_checked_at", "last_error")

    def clean(self):
        data = super().clean()
        if data.get("enabled") and not (data.get("new_password") or (self.instance and self.instance.has_password())):
            raise forms.ValidationError("Cannot enable a login that has no password saved.")
        return data

    def save(self, commit=True):
        obj = super().save(commit=False)
        if self.cleaned_data.get("new_password"):
            obj.set_password(self.cleaned_data["new_password"])
            obj.consecutive_failures = 0
        if commit:
            obj.save()
        return obj


class LogInline(admin.TabularInline):
    model = CarrierCredentialLog
    extra = 0
    can_delete = False
    readonly_fields = ("action", "actor", "detail", "created_at")
    max_num = 0

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(CarrierCredential)
class CarrierCredentialAdmin(admin.ModelAdmin):
    form = CarrierCredentialForm
    list_display = ("carrier_key", "line", "label", "organization", "enabled", "status", "password_saved", "last_checked_at")
    list_filter = ("enabled", "status", "line", "carrier_key", "organization")
    search_fields = ("carrier_key", "label", "username")
    readonly_fields = ("last_checked_at", "last_error", "consecutive_failures")
    inlines = [LogInline]
    actions = ["enable_selected", "disable_selected"]

    @admin.display(boolean=True, description="Password saved")
    def password_saved(self, obj):
        return obj.has_password()

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        CarrierCredentialLog.objects.create(
            credential=obj, action="updated" if change else "created", actor=str(request.user)[:100],
            detail="password changed" if form.cleaned_data.get("new_password") else "",
        )

    @admin.action(description="Enable selected logins")
    def enable_selected(self, request, qs):
        for c in qs.exclude(password_enc=""):
            c.enabled = True
            c.save(update_fields=["enabled", "updated_at"])
            CarrierCredentialLog.objects.create(credential=c, action="enabled", actor=str(request.user)[:100])

    @admin.action(description="Disable selected logins")
    def disable_selected(self, request, qs):
        for c in qs:
            c.enabled = False
            c.save(update_fields=["enabled", "updated_at"])
            CarrierCredentialLog.objects.create(credential=c, action="disabled", actor=str(request.user)[:100])
