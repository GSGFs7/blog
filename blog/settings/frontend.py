from .base import DEBUG
from .env import get_bool, get_int, get_str

APP_BUILD_ID = get_str("APP_BUILD_ID")
if not APP_BUILD_ID:
    if not DEBUG:
        raise RuntimeError("APP_BUILD_ID is required when DEBUG is disabled")
    APP_BUILD_ID = "local"

SOLID_ISLANDS_SSR = get_bool("SOLID_ISLANDS_SSR", not DEBUG)
PAGE_NAVIGATION_MODE = get_str("PAGE_NAVIGATION_MODE", "auto")

# dev
VITE_PORT = get_int("VITE_PORT", 5173)
VITE_DEV_SERVER_URL = f"http://localhost:{VITE_PORT}"
VITE_DEV_SERVER_WS_URL = f"ws://localhost:{VITE_PORT}"
