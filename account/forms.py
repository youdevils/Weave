from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordResetForm
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.template.loader import render_to_string
from django.urls import reverse

from account.models import CustomUser
from account.services.emails import send_email


class SignupForm(forms.Form):
    email = forms.EmailField(max_length=254)
    password1 = forms.CharField(widget=forms.PasswordInput, strip=False)
    password2 = forms.CharField(widget=forms.PasswordInput, strip=False)

    def clean_email(self):
        email = self.cleaned_data["email"]

        if CustomUser.objects.filter(email__iexact=email).exists():
            raise ValidationError("An account with this email already exists.")

        return email

    def clean_password2(self):
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")

        if password1 and password2 and password1 != password2:
            raise ValidationError("The two password fields didn't match.")

        if password2:
            try:
                validate_password(
                    password2,
                    user=CustomUser(email=self.cleaned_data.get("email", "")),
                )
            except ValidationError as error:
                self.add_error("password2", error)

        return password2


class EmailAuthenticationForm(AuthenticationForm):
    # AuthenticationForm.clean() and authenticate() both read "username"
    # regardless of USERNAME_FIELD — the field stays named "username",
    # just typed and labelled as an email address.
    username = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(attrs={"autofocus": True, "autocomplete": "email"}),
    )

    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": "Please enter a correct email address and password.",
    }


class ResendPasswordResetForm(PasswordResetForm):
    def send_mail(
        self,
        subject_template_name,
        email_template_name,
        context,
        from_email,
        to_email,
        html_email_template_name=None,
    ):
        path = reverse(
            "account:password_reset_confirm",
            kwargs={"uidb64": context["uid"], "token": context["token"]},
        )
        reset_url = f"{context['protocol']}://{context['domain']}{path}"

        html = render_to_string(
            "account/email/password_reset.html",
            {"reset_url": reset_url, "user": context["user"]},
        )

        send_email(to=to_email, subject="Reset your OnyxJar password", html=html)
