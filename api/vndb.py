import os
from typing import List, Optional, TypedDict

import httpx2


class Title(TypedDict):
    title: str
    lang: str


class Image(TypedDict):
    url: str


class VNItem(TypedDict):
    id: str
    alttitle: Optional[str]
    rating: float
    title: str
    titles: List[Title]
    image: Image


class VNDBResponse(TypedDict):
    results: List[VNItem]
    more: bool


def query_vn(id: str) -> VNDBResponse:
    fields = [
        "title",
        "alttitle",
        "titles.lang",
        "titles.title",
        "image.url",
        "rating",
    ]

    res = httpx2.post(
        "https://api.vndb.org/kana/vn",
        headers={
            "Content-Type": "application/json",
            "User-Agent": f"Django (+https://{os.getenv('DOMAIN', 'Unknown')})",
        },
        json={
            "filters": ["id", "=", id],
            "fields": ", ".join(fields),
        },
    )

    return res.json()
