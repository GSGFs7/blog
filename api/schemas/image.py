from typing import Optional
from uuid import UUID

from ninja import Schema


class ImageUploadRequestSchema(Schema):
    uploader_type: str
    uploader_id: UUID
    alt_text: Optional[str] = None
    description: Optional[str] = None


class ImageUploadResponseSchema(Schema):
    id: int
    url: str
    width: Optional[int]
    height: Optional[int]
    original_name: str
