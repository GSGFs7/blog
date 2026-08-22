from ninja import Router, Status
from pydantic import PositiveInt

from api.models import Category, Post
from api.schemas import CategoryResponseSchema, MessageSchema

router = Router()


@router.get(
    "/{int:category_id}",
    response={200: CategoryResponseSchema, 400: MessageSchema, 404: MessageSchema},
)
async def category_get_post(
    request, category_id: int, page: PositiveInt = 1, size: PositiveInt = 10
):
    try:
        category = await Category.objects.aget(pk=category_id)
        posts_qs = Post.objects.filter(category=category)

        offset = (page - 1) * size
        total = await posts_qs.acount()

        if 0 < total <= offset:
            return Status(400, {"message": "Out of range"})

        return Status(
            200,
            {
                "posts": [p async for p in posts_qs[offset : offset + size]],
                "pagination": {
                    "total": total,
                    "page": page,
                    "size": size,
                },
                "name": category.name,
            },
        )
    except Category.DoesNotExist:
        return Status(404, {"message": f"Category 'id={category_id}' not found"})
