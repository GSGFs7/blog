import json
from functools import lru_cache

from django.conf import settings


@lru_cache(maxsize=1)
def music_placeholder() -> str:
    path = settings.BASE_DIR / "web/static/ssr/solid-islands.json"
    return json.loads(path.read_text())["staticIslands"]["MusicTrack"]
