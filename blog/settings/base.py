from .env import BASE_DIR, get_str, is_debug

DEBUG = is_debug()

# Application definition
INSTALLED_APPS = [
    "django.contrib.postgres",
    "accounts.apps.TwoFactorAdminConfig",
    "django.contrib.auth",
    "django.contrib.sitemaps",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "ninja",
    "django_otp",
    "django_otp.plugins.otp_static",
    "django_otp.plugins.otp_totp",
    "accounts.apps.AccountsConfig",
    "django_celery_beat",
    "django_prometheus",
    "api.apps.ApiConfig",
    "media_service.apps.MediaServiceConfig",
    "web.apps.WebConfig",
]

MIDDLEWARE = [
    "django_prometheus.middleware.PrometheusBeforeMiddleware",
    "core.middleware.HeadersMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "core.middleware.NormalizeTrailingSlashMiddleware",
    "django.middleware.csp.ContentSecurityPolicyMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "api.middleware.OAuthGuestMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django_otp.middleware.OTPMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "web.middleware.HtmxMiddleware",
    "django_prometheus.middleware.PrometheusAfterMiddleware",
]

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": not DEBUG,
        "OPTIONS": {
            # disable template cache in DEBUG
            **(
                {
                    "loaders": [
                        "django.template.loaders.filesystem.Loader",
                        "django.template.loaders.app_directories.Loader",
                    ]
                }
                if DEBUG
                else {}
            ),
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "web.context_processors.site_meta",
            ],
        },
    },
]

WSGI_APPLICATION = "blog.wsgi.application"
ASGI_APPLICATION = "blog.asgi.application"

ROOT_URLCONF = "blog.urls"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# URL normalization
APPEND_SLASH = False

# Internationalization
# https://docs.djangoproject.com/en/6.0/topics/i18n/
LANGUAGE_CODE = "zh-hans"
TIME_ZONE = "Asia/Shanghai"
USE_I18N = True
USE_TZ = True

# logging
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": get_str("DJANGO_LOGLEVEL", "INFO").upper(),
    },
}

# Django-ninja
NINJA_PAGINATION_CLASS = "api.pagination.Pagination"

# Test runner configuration
# Use custom QuietTestRunner to suppress noisy log output during tests
TEST_RUNNER = "api.tests.runner.QuietTestRunner"

# DEBUG settings
# if DEBUG:
#     try:
#         import debug_toolbar  # noqa
#     except ImportError:
#         pass
#     else:
#         # django-debug-toolbar
#         INSTALLED_APPS.append(
#             "debug_toolbar",
#         )
#         MIDDLEWARE.insert(
#             MIDDLEWARE.index("web.middleware.HtmxMiddleware"),
#             "debug_toolbar.middleware.DebugToolbarMiddleware",
#         )
#         INTERNAL_IPS = [
#             "127.0.0.1",
#         ]
