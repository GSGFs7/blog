from django.utils.csp import CSP

from .env import get_list, get_str, is_debug, is_k8s_env, require
from .frontend import VITE_DEV_SERVER_URL, VITE_DEV_SERVER_WS_URL

_K8S_ENV = is_k8s_env()

SECRET_KEY = require("DJANGO_SECRET_KEY")

IMAGE_CDN_ORIGIN = "https://img.gsgfs.moe"
STATIC_CDN_ORIGIN = "https://static.gsgfs.moe"

# proxy
USE_X_FORWARDED_HOST = True
USE_X_FORWARDED_PORT = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
TRUSTED_PROXY_CIDRS = tuple(get_list("TRUSTED_PROXY_CIDRS"))

# csrf
CSRF_TRUSTED_ORIGINS = (
    get_list("DJANGO_CSRF_TRUSTED_ORIGINS")
    if get_str("DJANGO_CSRF_TRUSTED_ORIGINS")
    else []
)

if _K8S_ENV:
    ALLOWED_HOSTS = ["*"]
else:
    ALLOWED_HOSTS = get_list(
        "DJANGO_ALLOWED_HOSTS",
        "127.0.0.1,localhost",
    )

# disable HTTPS redirect to support health cache
SECURE_SSL_REDIRECT = not is_debug() and not _K8S_ENV
SESSION_COOKIE_SECURE = not is_debug()
CSRF_COOKIE_SECURE = not is_debug()
SECURE_CONTENT_TYPE_NOSNIFF = True

if not is_debug():
    SECURE_HSTS_SECONDS = 31536000  # 1y
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
else:
    SECURE_HSTS_SECONDS = 0
    SECURE_HSTS_INCLUDE_SUBDOMAINS = False
    SECURE_HSTS_PRELOAD = False


# CSP
CSP_POLICY = {
    "default-src": [CSP.SELF, IMAGE_CDN_ORIGIN],  # prefetch imgs
    "base-uri": [CSP.NONE],
    "object-src": [CSP.NONE],
    "frame-src": [CSP.NONE],
    "frame-ancestors": [CSP.NONE],
    "form-action": [CSP.SELF],
    "script-src": [CSP.SELF, CSP.WASM_UNSAFE_EVAL, STATIC_CDN_ORIGIN],
    "script-src-attr": [CSP.NONE],
    # xterm.js needs inline style
    "style-src": [CSP.SELF, CSP.UNSAFE_INLINE, STATIC_CDN_ORIGIN],
    "style-src-attr": [CSP.UNSAFE_INLINE],
    "img-src": [CSP.SELF, "data:", "blob:", IMAGE_CDN_ORIGIN, STATIC_CDN_ORIGIN],
    "font-src": [CSP.SELF, "data:", STATIC_CDN_ORIGIN],
    "connect-src": [CSP.SELF, STATIC_CDN_ORIGIN],
    "worker-src": [CSP.SELF, "blob:", STATIC_CDN_ORIGIN],
    "media-src": [CSP.SELF],
    "manifest-src": [CSP.SELF],
}
if is_debug():
    CSP_POLICY["script-src"].append(VITE_DEV_SERVER_URL)
    CSP_POLICY["style-src"].append(VITE_DEV_SERVER_URL)
    CSP_POLICY["font-src"].append(VITE_DEV_SERVER_URL)
    CSP_POLICY["connect-src"].extend([VITE_DEV_SERVER_URL, VITE_DEV_SERVER_WS_URL])
    CSP_POLICY["worker-src"].append(VITE_DEV_SERVER_URL)
else:
    CSP_POLICY["upgrade-insecure-requests"] = True

SECURE_CSP = CSP_POLICY


FERNET_KEY = require("FERNET_KEY")
FERNET_OLD_KEYS = get_list("FERNET_OLD_KEYS")

# Password validation
# https://docs.djangoproject.com/en/6.0/ref/settings/#auth-password-validators
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",  # noqa: E501
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]
