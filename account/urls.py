from django.contrib.auth import views as auth_views
from django.urls import path

from .views import views

app_name = "account"

urlpatterns = [
    path("login/", views.LoginView.as_view(), name="login"),
    path("signup/", views.signup, name="signup"),
    path("logout/", auth_views.LogoutView.as_view(next_page="website:home"), name="logout"),
    path("verify-email/<uidb64>/<token>/", views.verify_email, name="verify_email"),
    path("verify-email/resend/", views.resend_verification, name="resend_verification"),
    path("password-reset/", views.PasswordResetView.as_view(), name="password_reset"),
    path("password-reset/<uidb64>/<token>/", views.PasswordResetConfirmView.as_view(), name="password_reset_confirm"),
]
