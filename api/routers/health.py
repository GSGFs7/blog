from ninja import Router

from ..schemas import (
    MessageSchema,
)

router = Router()


@router.get("", response=MessageSchema)
async def heath_status(request):
    return {"message": "OK"}
