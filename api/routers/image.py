import logging

from django.conf import settings
from ninja import Form, Router, Status, UploadedFile

from api.auth import AsyncTimeBaseAuth
from api.schemas import (
    ImageUploadRequestSchema,
    ImageUploadResponseSchema,
    MessageSchema,
)
from media_service.constants import IMAGE_ALLOWED_FORMAT
from media_service.services.image import AsyncImageService

router = Router()
logger = logging.getLogger(__name__)


# in this endpoint, only allow Guest upload
ALLOWED_UPLOADER_TYPES = {"api.guest"}


@router.post(
    "/upload",
    response={201: ImageUploadResponseSchema, 400: MessageSchema},
    auth=AsyncTimeBaseAuth(),
)
async def upload_test(
    request,
    file: UploadedFile,
    data: Form[ImageUploadRequestSchema],
):
    if file.content_type not in IMAGE_ALLOWED_FORMAT:
        return Status(400, {"message": "not allowed image types"})

    if file.size > settings.IMAGE_UPLOAD_MAX_SIZE:
        return Status(400, {"message": "image size exceeds maximum limit"})

    if data.uploader_type.lower() not in ALLOWED_UPLOADER_TYPES:
        return Status(400, {"message": "not allowed uploader types"})

    try:
        uploader = await AsyncImageService.get_uploader(
            data.uploader_type, data.uploader_id
        )
    except Exception:
        return Status(400, {"message": "error when getting actor"})

    img, img_res, _ = await AsyncImageService.upload_image(
        content=file,
        filename=file.name,
        alt_text=data.alt_text or "",
        description=data.description or "",
        uploader=uploader,
        metadata={
            "uploaded_via": str(request.auth),
            "uploader_type": data.uploader_type,
            "uploader_id": data.uploader_id,
        },
    )

    return Status(
        201,
        ImageUploadResponseSchema(
            id=img.id,
            url=img_res.file.url,
            width=img_res.width,
            height=img_res.height,
            original_name=img.original_name,
        ),
    )
