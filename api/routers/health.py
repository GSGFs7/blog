from ninja import Router

from api.schemas import (
    MessageSchema,
)

router = Router()


@router.get("", response=MessageSchema)
async def heath_status(request):
    return {"message": "OK"}
