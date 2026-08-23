from typing import TypedDict

from ._markdown_it_rs_py import (
    FrontMatter,
    MarkdownIt,
    RenderPlan,
)


class _OptionalImageMetadata(TypedDict, total=False):
    avif_src: str | None
    webp_src: str | None
    width: int | None
    height: int | None
    placeholder: str | None


class ImageMetadata(_OptionalImageMetadata):
    src: str


__all__ = [
    "FrontMatter",
    "ImageMetadata",
    "MarkdownIt",
    "RenderPlan",
]
