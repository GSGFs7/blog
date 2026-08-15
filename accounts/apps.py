from django.apps import AppConfig
from django.contrib.admin.apps import AdminConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"


# apply some patch to django admin
class TwoFactorAdminConfig(AdminConfig):
    default_site = "accounts.admin.TwoFactorAdminSite"
