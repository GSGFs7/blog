from ninja import Router, Status
from pydantic import PositiveInt

from api.models import Anime
from api.schemas import AnimeIds, AnimeSchema, MessageSchema

router = Router()


@router.get("/ids", response={200: AnimeIds, 400: MessageSchema, 404: MessageSchema})
async def get_all_anime_ids(request, page: PositiveInt = 1, size: PositiveInt = 10):
    offset = (page - 1) * size
    total = await Anime.objects.acount()

    if total == 0:
        return Status(404, {"message": "Empty"})

    if offset >= total:
        return Status(400, {"message": "Out of range"})

    anime = [a async for a in Anime.objects.all()[offset : offset + size]]
    return Status(
        200,
        {
            "ids": anime,
            "pagination": {
                "total": total,
                "page": page,
                "size": size,
            },
        },
    )


@router.get("/{int:anime_id}", response={200: AnimeSchema, 404: MessageSchema})
async def get_anime(request, anime_id: int):
    try:
        return await Anime.objects.aget(pk=anime_id)
    except Anime.DoesNotExist:
        return Status(404, {"message": "Not found"})
