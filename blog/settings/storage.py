from .base import BASE_DIR
from .env import get_bool, get_str
from .security import IMAGE_CDN_ORIGIN

# https://docs.djangoproject.com/en/6.0/howto/static-files/
STATIC_URL = get_str("STATIC_URL", "/static/")
STATIC_ROOT = BASE_DIR / "staticfiles"

# Media files
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# img
USE_S3 = get_bool("USE_S3", False)
S3_BUCKET_NAME = get_str("S3_BUCKET_NAME")
S3_ENDPOINT_URL = get_str("S3_ENDPOINT_URL")
S3_ACCESS_KEY_ID = get_str("S3_ACCESS_KEY_ID")
S3_SECRET_ACCESS_KEY = get_str("S3_SECRET_ACCESS_KEY")
S3_PUBLIC_DOMAIN = get_str("S3_PUBLIC_DOMAIN")

IMAGE_UPLOAD_MAX_SIZE = 20971520  # 20MiB
DATA_UPLOAD_MAX_MEMORY_SIZE = 20971520  # 20MiB

IMAGE_PICTURE_URL_PREFIXES = {
    f"{IMAGE_CDN_ORIGIN}/images/raw/": {
        "avif": f"{IMAGE_CDN_ORIGIN}/images/avif/",
        "webp": f"{IMAGE_CDN_ORIGIN}/images/webp/",
    }
}


def _storage_backend():
    if not USE_S3:
        return {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        }

    if not all(
        [S3_BUCKET_NAME, S3_ENDPOINT_URL, S3_ACCESS_KEY_ID, S3_SECRET_ACCESS_KEY]
    ):
        raise RuntimeError("S3 storage is not fully configured")

    options = {
        "bucket_name": S3_BUCKET_NAME,
        "endpoint_url": S3_ENDPOINT_URL,
        "access_key": S3_ACCESS_KEY_ID,
        "secret_key": S3_SECRET_ACCESS_KEY,
        "querystring_auth": False,  # public bucket
    }
    if S3_PUBLIC_DOMAIN:
        options["custom_domain"] = S3_PUBLIC_DOMAIN

    return {
        "BACKEND": "media_service.backends.MediaStorage",
        "OPTIONS": options,
    }


STORAGES = {
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.ManifestStaticFilesStorage",
    },
    "default": _storage_backend(),
}
