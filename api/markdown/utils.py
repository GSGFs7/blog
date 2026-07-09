import re
import tomllib
from collections.abc import Sequence
from typing import Any

import yaml
from markdown_it_rs_py import FrontMatter, Node

__all__ = ["extract_toc", "parse_frontmatter"]


def extract_toc(nodes: Sequence[Node]) -> list[dict[str, Any]]:
    toc = []
    for node in nodes:
        if "heading" in node.type_name.lower():
            item = extract_toc_item(node.render())
            if item:
                toc.append(item)
    return toc


def extract_toc_item(html: str) -> dict[str, Any] | None:
    match = re.search(r'<h(\d) id="([^"]*)">(.*)</h\1>', html)
    if not match:
        return None

    return {
        "level": int(match.group(1)),
        "slug": match.group(2),
        "text": re.sub(r"<[^>]*>", "", match.group(3)),
    }


def parse_frontmatter(frontmatter: FrontMatter) -> dict[str, Any]:
    if frontmatter.kind == "yaml":
        return yaml.safe_load(frontmatter.raw)
    elif frontmatter.kind == "toml":
        return tomllib.loads(frontmatter.raw)
    else:
        return {}
