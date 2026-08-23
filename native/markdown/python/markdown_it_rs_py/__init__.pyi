from collections.abc import Sequence
from typing import Any, Mapping, TypedDict

class _OptionalImageMetadata(TypedDict, total=False):
    avif_src: str | None
    webp_src: str | None
    width: int | None
    height: int | None
    placeholder: str | None

class ImageMetadata(_OptionalImageMetadata):
    src: str

class FrontMatter:
    @property
    def kind(self) -> str: ...
    @property
    def raw(self) -> str: ...

class RenderPlan:
    @property
    def image_checksums(self) -> tuple[str, ...]: ...
    @property
    def toc(self) -> list[dict[str, Any]]: ...
    @property
    def frontmatter(self) -> FrontMatter | None: ...
    def finish(self, images: Mapping[str, ImageMetadata] | None = None) -> str: ...

class MarkdownIt:
    def __init__(self) -> None: ...
    def prepare(
        self,
        src: str,
        *,
        include_toc: bool = False,
        include_frontmatter: bool = False,
        image_picture_source_prefixes: Sequence[str] = (),
    ) -> RenderPlan: ...
