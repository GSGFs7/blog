from django.urls import path

from accounts import views

app_name = "accounts"

urlpatterns = [
    path("two_factor/verify/", views.verify_view, name="verify"),
    path("two_factor/setup/", views.setup_view, name="setup"),
    path("two_factor/qrcode/", views.qr_code_view, name="qr"),
]
