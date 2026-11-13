from typing import IO
from uuid import UUID

from django.apps import apps
from django.db import models

from media_service.models import Image, ImageResource

# TODO: move Image create logic to here


class AsyncImageService:
    @staticmethod
    async def get_uploader(
        uploader_type: str, uploader_id: int | str | UUID
    ) -> models.Model:
        model_class = apps.get_model(uploader_type)
        return await model_class.objects.aget(pk=uploader_id)

    @staticmethod
    async def upload_image(
        content: IO[bytes],
        filename: str,
        alt_text: str = "",
        description: str = "",
        uploader: models.Model = None,
        metadata: dict | None = None,
    ) -> tuple["Image", ImageResource, bool]:
        return await Image.acreate_from_file(
            content, filename, alt_text, description, uploader, metadata
        )


class SyncImageService:
    @staticmethod
    def get_uploader(uploader_type: str, uploader_id: int | str | UUID) -> models.Model:
        model_class = apps.get_model(uploader_type)
        return model_class.objects.get(pk=uploader_id)

    @staticmethod
    def upload_image(
        content: IO[bytes],
        filename: str,
        alt_text: str = "",
        description: str = "",
        uploader: models.Model = None,
        metadata: dict | None = None,
    ) -> tuple["Image", ImageResource, bool]:
        return Image.create_from_file(
            content, filename, alt_text, description, uploader, metadata
        )
