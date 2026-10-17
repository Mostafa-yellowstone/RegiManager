from django import forms
from django.contrib.auth import views as auth_views
from django.contrib.auth.forms import PasswordResetForm, SetPasswordForm
from django.http import HttpResponseRedirect
from django.urls import reverse, reverse_lazy

from .ratelimit import clear_login_failures, consume_rate_limit

RESET_EMAILS_PER_ADDRESS = 3
RESET_EMAIL_WINDOW_SECONDS = 60 * 60

_SIGN_IN_FOOTER = {
    "auth_icon": "key",
    "switch_label": "Remembered it?",
    "switch_url": "login",
    "switch_text": "Back to sign in",
}


class RegiPasswordResetForm(PasswordResetForm):
    email = forms.EmailField(
        label="Email address",
        max_length=254,
        widget=forms.EmailInput(attrs={"autocomplete": "email", "autofocus": True, "placeholder": "you@company.com"}),
    )


class RegiSetPasswordForm(SetPasswordForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("new_password1", "new_password2"):
            self.fields[name].widget.attrs.update({"autocomplete": "new-password"})
        self.fields["new_password1"].widget.attrs["autofocus"] = True


class RegiPasswordResetView(auth_views.PasswordResetView):
    template_name = "core/auth_form.html"
    form_class = RegiPasswordResetForm
    subject_template_name = "registration/regimanager_password_reset_subject.txt"
    email_template_name = "registration/regimanager_password_reset_email.txt"
    html_email_template_name = "registration/regimanager_password_reset_email.html"
    success_url = reverse_lazy("password-reset-done")
    extra_context = {
        **_SIGN_IN_FOOTER,
        "title": "Reset your password",
        "subtitle": "Enter the email on your account and we'll send you a secure reset link.",
        "submit_text": "Send Reset Link",
        "loading_text": "Sending link…",
    }

    def form_valid(self, form):
        email = form.cleaned_data["email"].strip().lower()
        # Same redirect either way so the response never reveals whether the address has an account
        # or that sending was throttled.
        if not consume_rate_limit(
            f"pwreset-email:{email}",
            limit=RESET_EMAILS_PER_ADDRESS,
            window_seconds=RESET_EMAIL_WINDOW_SECONDS,
        ):
            return HttpResponseRedirect(self.get_success_url())
        return super().form_valid(form)


class RegiPasswordResetDoneView(auth_views.PasswordResetDoneView):
    template_name = "core/auth_form.html"
    extra_context = {
        **_SIGN_IN_FOOTER,
        "title": "Check your email",
        "subtitle": "Reset link on its way.",
        "info_text": (
            "If an account matches that email, we've sent a link to set a new password. "
            "It expires in 1 hour. Check your spam folder if it doesn't arrive within a few minutes."
        ),
    }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["action_url"] = reverse("login")
        context["action_text"] = "Back to sign in"
        return context


class RegiPasswordResetConfirmView(auth_views.PasswordResetConfirmView):
    template_name = "core/auth_form.html"
    form_class = RegiSetPasswordForm
    success_url = reverse_lazy("password-reset-complete")
    post_reset_login = False
    extra_context = {
        **_SIGN_IN_FOOTER,
        "title": "Set a new password",
        "subtitle": "Choose a strong password you don't use anywhere else.",
        "submit_text": "Update Password",
        "loading_text": "Updating password…",
    }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if not context.get("validlink"):
            context.update(
                {
                    "title": "Link expired",
                    "subtitle": "This password reset link is invalid or has already been used.",
                    "info_text": "Reset links work once and expire after 1 hour. Request a new one to continue.",
                    "action_url": reverse("password-reset"),
                    "action_text": "Request a new link",
                }
            )
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        username = form.user.get_username()
        for scope in ("web", "admin"):
            clear_login_failures(scope, username, self.request)
        return response


class RegiPasswordResetCompleteView(auth_views.PasswordResetCompleteView):
    template_name = "core/auth_form.html"
    extra_context = {
        **_SIGN_IN_FOOTER,
        "switch_label": "Need help?",
        "switch_url": "contact",
        "switch_text": "Contact support",
        "title": "Password updated",
        "subtitle": "You're all set.",
        "info_text": "Your password has been changed and other signed-in sessions were signed out. Sign in with your new password.",
    }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["action_url"] = reverse("login")
        context["action_text"] = "Sign in"
        return context
