"""
Public account pages: signup, login, logout, email verification, and
password reset.

Login, logout, and password reset are thin subclasses of Django's built-in
auth views — their token/session handling (safe "next" redirects, the
one-time-use password-reset link swap) is security-sensitive and already
correct, so it isn't reimplemented here.
"""

from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import SetPasswordForm
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from account.forms import EmailAuthenticationForm, ResendPasswordResetForm, SignupForm
from account.models import CustomUser
from account.services.emails import send_verification_email
from account.tokens import email_verification_token
from workspace.models import Workspace, WorkspaceMember


@require_http_methods(["GET", "HEAD", "POST"])
def signup(request):
    if request.user.is_authenticated:
        return redirect("workspace:index")

    if request.method == "POST":
        form = SignupForm(request.POST)

        if form.is_valid():
            try:
                with transaction.atomic():
                    user = CustomUser.objects.create_user(
                        email=form.cleaned_data["email"],
                        password=form.cleaned_data["password1"],
                    )
                    workspace = Workspace.objects.create(name="My Workspace")
                    WorkspaceMember.objects.create(
                        workspace=workspace,
                        user=user,
                        role=WorkspaceMember.Role.OWNER,
                    )
            except (ValidationError, IntegrityError):
                # Another signup for the same email won the race between our
                # clean_email() check and the database's unique constraint.
                form.add_error("email", "An account with this email already exists.")
            else:
                auth_login(request, user)
                send_verification_email(request, user)
                return redirect("workspace:index")
    else:
        form = SignupForm()

    return render(
        request,
        "account/signup.html",
        {
            "form": form,
            "page_title": "Try OnyxJar free",
            "page_description": "Create your OnyxJar account. Free during beta.",
        },
    )


class LoginView(auth_views.LoginView):
    form_class = EmailAuthenticationForm
    template_name = "account/login.html"
    redirect_authenticated_user = True

    def get_context_data(self, **kwargs):
        return {
            **super().get_context_data(**kwargs),
            "page_title": "Log in — OnyxJar",
            "page_description": "Log in to OnyxJar.",
        }


@require_GET
def verify_email(request, uidb64, token):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = CustomUser.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, CustomUser.DoesNotExist):
        user = None

    if user is not None and email_verification_token.check_token(user, token):
        user.email_verified = True
        user.save(update_fields=["email_verified"])
        messages.success(request, "Your email address has been verified.")
    else:
        messages.error(request, "That verification link is invalid or has expired.")

    return redirect("workspace:index")


@login_required
@require_POST
def resend_verification(request):
    if not request.user.email_verified:
        send_verification_email(request, request.user)
        messages.success(request, "Verification email sent.")

    return redirect("workspace:index")


class PasswordResetView(auth_views.PasswordResetView):
    form_class = ResendPasswordResetForm
    template_name = "account/password_reset.html"

    def get_success_url(self):
        return f"{reverse('account:password_reset')}?sent=1"

    def get_context_data(self, **kwargs):
        return {
            **super().get_context_data(**kwargs),
            "page_title": "Reset your password — OnyxJar",
            "page_description": "Reset your OnyxJar password.",
        }


class PasswordResetConfirmView(auth_views.PasswordResetConfirmView):
    form_class = SetPasswordForm
    template_name = "account/password_reset_confirm.html"
    post_reset_login = True
    post_reset_login_backend = "django.contrib.auth.backends.ModelBackend"
    success_url = reverse_lazy("workspace:index")

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "Your password has been reset.")
        return response

    def get_context_data(self, **kwargs):
        return {
            **super().get_context_data(**kwargs),
            "page_title": "Choose a new password — OnyxJar",
            "page_description": "Choose a new OnyxJar password.",
        }
