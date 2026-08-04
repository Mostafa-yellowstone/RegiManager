"""Forms for the agent portal."""

from django import forms

from .agent_portal_models import AgentTask
from .models import OrganizationMembership


class AgentProfilePhotoForm(forms.ModelForm):
    class Meta:
        model = OrganizationMembership
        fields = ("profile_photo",)
        widgets = {
            "profile_photo": forms.ClearableFileInput(
                attrs={
                    "accept": "image/jpeg,image/png,image/webp",
                    "class": "agent-photo-input",
                    "id": "agent-photo-input",
                }
            )
        }

    def clean_profile_photo(self):
        photo = self.cleaned_data.get("profile_photo")
        if not photo:
            return photo
        if getattr(photo, "size", 0) > 5 * 1024 * 1024:
            raise forms.ValidationError("Image must be 5 MB or smaller.")
        content_type = getattr(photo, "content_type", "") or ""
        if content_type and content_type not in {"image/jpeg", "image/png", "image/webp"}:
            raise forms.ValidationError("Use a JPG, PNG, or WebP image.")
        return photo


class AgentTaskAssignForm(forms.ModelForm):
    class Meta:
        model = AgentTask
        fields = ("assigned_to", "title", "description", "due_date")
        widgets = {
            "assigned_to": forms.Select(attrs={"class": "form-control"}),
            "title": forms.TextInput(attrs={"class": "form-control", "placeholder": "Task title", "maxlength": 200}),
            "description": forms.Textarea(
                attrs={"class": "form-control", "rows": 3, "placeholder": "Optional details"}
            ),
            "due_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
        }

    def __init__(self, *args, organization=None, fixed_assignee=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization = organization
        self.fixed_assignee = fixed_assignee
        qs = OrganizationMembership.objects.none()
        if organization is not None:
            qs = (
                OrganizationMembership.objects.filter(
                    organization=organization,
                    is_active=True,
                    user__is_active=True,
                    can_deal_with_insurance=True,
                )
                .select_related("user")
                .order_by("user__first_name", "user__username")
            )
        if fixed_assignee is not None:
            qs = qs.filter(pk=fixed_assignee.pk)
            self.fields["assigned_to"].queryset = qs
            self.fields["assigned_to"].initial = fixed_assignee.pk
            self.fields["assigned_to"].widget = forms.HiddenInput()
        else:
            self.fields["assigned_to"].queryset = qs
            self.fields["assigned_to"].empty_label = "Select insurance agent…"
            self.fields["assigned_to"].label_from_instance = (
                lambda m: m.user.get_full_name().strip() or m.user.username
            )
        self.fields["due_date"].required = False
        self.fields["description"].required = False

    def clean_assigned_to(self):
        assignee = self.cleaned_data.get("assigned_to")
        if self.fixed_assignee is not None and assignee and assignee.pk != self.fixed_assignee.pk:
            raise forms.ValidationError("Invalid assignee for this agent.")
        if assignee and not assignee.can_deal_with_insurance:
            raise forms.ValidationError("Tasks can only be assigned to insurance agents.")
        return assignee


class AgentTaskEditForm(forms.ModelForm):
    class Meta:
        model = AgentTask
        fields = ("assigned_to", "title", "description", "due_date", "completion_note")
        widgets = {
            "assigned_to": forms.Select(attrs={"class": "form-control"}),
            "title": forms.TextInput(attrs={"class": "form-control", "placeholder": "Task title", "maxlength": 200}),
            "description": forms.Textarea(
                attrs={"class": "form-control", "rows": 3, "placeholder": "Instructions / details"}
            ),
            "due_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "completion_note": forms.Textarea(
                attrs={"class": "form-control", "rows": 2, "placeholder": "Agent completion note"}
            ),
        }

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization = organization
        qs = OrganizationMembership.objects.none()
        if organization is not None:
            qs = (
                OrganizationMembership.objects.filter(
                    organization=organization,
                    is_active=True,
                    user__is_active=True,
                    can_deal_with_insurance=True,
                )
                .exclude(role=OrganizationMembership.Role.OWNER)
                .select_related("user")
                .order_by("user__first_name", "user__username")
            )
        self.fields["assigned_to"].queryset = qs
        self.fields["assigned_to"].label_from_instance = (
            lambda m: m.user.get_full_name().strip() or m.user.username
        )
        self.fields["due_date"].required = False
        self.fields["description"].required = False
        self.fields["completion_note"].required = False

    def clean_assigned_to(self):
        assignee = self.cleaned_data.get("assigned_to")
        if assignee and not assignee.can_deal_with_insurance:
            raise forms.ValidationError("Tasks can only be assigned to insurance agents.")
        return assignee
