import json
from functools import lru_cache
from pathlib import Path

from django import template
from django.conf import settings
from django.utils.safestring import mark_safe

register = template.Library()


@lru_cache(maxsize=1)
def _load_manifest():
    manifest_path = Path(settings.STATIC_ROOT) / "dist" / "manifest.json"
    with manifest_path.open("r") as f:
        return json.load(f)


@register.simple_tag
def vite_asset(entry_point: str):
    if settings.DEBUG:
        return f"http://localhost:5173/{entry_point}"

    try:
        manifest = _load_manifest()
        return f"{settings.STATIC_URL}dist/{manifest[entry_point]['file']}"
    except FileNotFoundError as exc:
        raise RuntimeError(
            "Vite manifest not found. Run `pnpm run build` first."
        ) from exc
    except (KeyError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"Vite asset `{entry_point}` is missing from manifest.json."
        ) from exc


@register.simple_tag
def vite_hmr():
    if settings.DEBUG:
        return mark_safe(
            '<script type="module" src="http://localhost:5173/@vite/client"></script>'
        )
    return ""
