"""Comment schemas."""

import datetime
from typing import List, Optional

from ninja.schema import Schema

from .base import PaginationSchema


class CommentSchema(Schema):
    id: int
    content: str
    post_id: int
    guest_id: int
    guest_name: str
    created_at: datetime.datetime
    updated_at: datetime.datetime
    avatar: str

    @staticmethod
    def resolve_guest_name(obj):
        return obj.guest.name

    @staticmethod
    def resolve_avatar(obj):
        return obj.guest.avatar


class CommentPaginationResponse(Schema):
    comments: List[CommentSchema]
    pagination: PaginationSchema


class CommentResponse(Schema):
    comments: List[CommentSchema]


class CommentIdsSchema(Schema):
    ids: List[int]


class NewCommentMetadataSchema(Schema):
    user_agent: str
    platform: str
    browser: str
    browser_version: str
    OS: str


class NewCommentSchema(Schema):
    provider_key: str
    user_id: str
    content: str
    post_id: int
    metadata: Optional[NewCommentMetadataSchema]
