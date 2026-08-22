"""Sitemap schemas."""

import datetime
from typing import List

from ninja.schema import Schema
from pydantic import ConfigDict, Field, RootModel


class PostSitemapSchema(Schema):
    id: int
    slug: str
    updated_at: datetime.datetime = Field(alias="content_update_at")

    model_config = ConfigDict(
        validate_by_alias=True,
        validate_by_name=True,
    )


class PostIdsForSitemap(RootModel):
    root: List[PostSitemapSchema]
