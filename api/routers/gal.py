from typing import List

from ninja import Router, Status
from ninja.pagination import paginate

from api.auth import AsyncTimeBaseAuth
from api.models import Gal
from api.pagination import paginate_as
from api.schemas import (
    GalSchema,
    GalUpdateSchema,
    IdSchema,
    IdsSchema,
    MessageSchema,
)

router = Router()


@router.get("", response=List[GalSchema])
@paginate(paginate_as("gals", GalSchema))
async def get_all_gal(request):
    # makesure here is MainThread
    # print(threading.current_thread().name)
    return Gal.objects.all()


@router.get("/ids", response=IdsSchema)
async def get_gal_ids(request):
    return {
        "ids": [i async for i in Gal.objects.values_list("id", flat=True)],
    }


@router.get("/{int:gal_id}", response={200: GalSchema, 404: MessageSchema})
async def get_gal_from_id(request, gal_id: int):
    try:
        return Status(200, await Gal.objects.aget(pk=gal_id))
    except Gal.DoesNotExist:
        return Status(404, {"message": "not found"})


@router.post(
    "/{int:gal_id}",
    response={200: IdSchema, 400: MessageSchema, 404: MessageSchema},
    auth=AsyncTimeBaseAuth(),
)
async def update_gal(request, gal_id: int, body: GalUpdateSchema):
    if gal_id != body.id:
        return Status(400, {"message": "id not match"})

    try:
        gal = await Gal.objects.aget(pk=gal_id)

        # update fields
        for field, value in body.dict(exclude={"id"}).items():
            setattr(gal, field, value)

        # save change
        await gal.asave()

        return Status(200, {"id": gal_id})
    except Gal.DoesNotExist:
        return Status(404, {"message": "not found"})
    except Exception:
        return Status(400, {"message": "Update failed"})
