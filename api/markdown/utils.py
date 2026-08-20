import tomllib
from datetime import date, datetime, time
from math import isfinite
from typing import Any

import yaml
from markdown_it_rs_py import FrontMatter

__all__ = ["parse_frontmatter"]


def _normalize_frontmatter_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, str)):
        return value

    if isinstance(value, float):
        if not isfinite(value):
            raise ValueError("frontmatter floats must be finite")
        return value

    if isinstance(value, (datetime, date, time)):
        return value.isoformat()

    if isinstance(value, list):
        return [_normalize_frontmatter_value(item) for item in value]

    if isinstance(value, dict):
        normalized = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("frontmatter mapping keys must be strings")
            normalized[key] = _normalize_frontmatter_value(item)
        return normalized

    raise ValueError(f"unsupported frontmatter value: {type(value).__name__}")


def parse_frontmatter(frontmatter: FrontMatter) -> dict[str, Any]:
    if frontmatter.kind == "yaml":
        try:
            parsed = yaml.safe_load(frontmatter.raw)
        except yaml.YAMLError as error:
            raise ValueError("invalid YAML frontmatter") from error
    elif frontmatter.kind == "toml":
        parsed = tomllib.loads(frontmatter.raw)
    else:
        return {}

    if parsed is None:
        return {}
    if not isinstance(parsed, dict):
        raise ValueError("frontmatter must be a mapping")
    return _normalize_frontmatter_value(parsed)
