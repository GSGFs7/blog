import logging
from typing import Any, List, Tuple

from asgiref.sync import sync_to_async
from django.core.cache import cache
from django.http import HttpRequest
from django.views.decorators.cache import cache_page
from ninja import Field, Router, Schema
from ninja.decorators import decorate_view
from ninja.errors import HttpError
from ninja.pagination import paginate

from api.models import Post
from api.pagination import Pagination, paginate_as
from api.post_search import post_search
from api.rate_limit import rate_limit
from api.schemas import (
    IdsSchema,
    MessageSchema,
    PaginationSchema,
    PostCardSchema,
    PostCardWithSimilarity,
    PostIdsForSitemap,
    PostSchema,
    PostSitemapSchema,
)
from core.hash import calculate_blake3_hash

router = Router()


@router.get("", response=List[PostCardSchema])
@paginate(paginate_as("posts", PostCardSchema))
async def get_all_posts(request):
    return (
        Post.objects.select_related("category")
        .prefetch_related("tags")
        .filter(status="published")
    )


@router.get("/ids", response=IdsSchema)
async def get_all_post_ids(request):
    return {
        "ids": [
            i
            async for i in Post.objects.filter(status="published").values_list(
                "id", flat=True
            )
        ],
    }


@router.get("/sitemap", response=PostIdsForSitemap)
async def get_all_post_ids_for_sitemap(request):
    posts = Post.objects.filter(status="published").values(
        "id", "slug", "content_update_at"
    )
    # transform to Pydantic model
    post_schemas = [PostSitemapSchema(**post) async for post in posts]
    return PostIdsForSitemap(root=post_schemas)


class PostSimilarityPagination(Pagination):
    class Input(Schema):
        page: int = Field(1, ge=1)
        size: int = Field(30, ge=1, le=100)  # 30 results by default

    class Output(Schema):
        posts_with_similarity: List[PostCardWithSimilarity]
        pagination: PaginationSchema

    items_attribute: str = "posts_with_similarity"

    async def apaginate_queryset(
        self,
        posts_with_similarities: Tuple[List[Post], List[float]],
        pagination: Pagination.Input,
        request: HttpRequest,
        **params: Any,
    ) -> dict:
        posts, similarities = posts_with_similarities
        offset = (pagination.page - 1) * pagination.size
        total = len(posts)

        return {
            "posts_with_similarity": [
                {"post": q, "similarity": similarities[offset + i]}
                for i, q in enumerate(posts[offset : offset + pagination.size])
            ],
            "pagination": {
                "page": pagination.page,
                "size": pagination.size,
                "total": total,
            },
        }


@router.get(
    "/search",
    response={
        200: List[PostCardWithSimilarity],
        400: MessageSchema,
        429: MessageSchema,
    },
)
@rate_limit(key_prefix="post_search", max_requests=50, window=1)
@decorate_view(cache_page(3600))  # 1h
@paginate(PostSimilarityPagination)
async def get_post_cards_from_query(request, q: str):
    # length limit
    q = q.strip()
    if len(q) > 200:
        # use an error to passby paginate decorator
        raise HttpError(400, "Query too long")

    # caching
    hashed_query = calculate_blake3_hash(q)
    cache_key = f"post_search:{hashed_query}"
    if not (result := await cache.aget(cache_key, False)):
        # query the search
        result = await sync_to_async(post_search)(q)
        await cache.aset(cache_key, result, timeout=7200)  # 2h

    # map the relation
    similarities_map = {r["id"]: r["hybrid_score"] for r in result}
    post_ids = [r["id"] for r in result]

    # query from db, maybe disordered
    posts_dict = {
        p.id: p
        async for p in Post.objects.filter(id__in=post_ids, status="published")
        .select_related("category")
        .prefetch_related("tags")
    }

    # recover the relation
    ordered_posts = []
    ordered_similarities = []
    for pid in post_ids:
        if pid in posts_dict:
            ordered_posts.append(posts_dict[pid])
            ordered_similarities.append(similarities_map[pid])

    # return to paginate decorator
    return ordered_posts, ordered_similarities


@router.get(
    "/latest", response={200: PostSchema, 404: MessageSchema, 500: MessageSchema}
)
async def get_latest_post(request):
    try:
        return await (
            Post.objects.select_related("category")
            .prefetch_related("tags")
            .filter(status="published")
            .alatest()
        )
    except Post.DoesNotExist:
        return 404, {"message": "Not found"}
    except Exception as e:
        logging.error(e)
        return 500, {"message": "Internal Server Error"}


@router.get(
    "/{int:post_id}",
    response={200: PostSchema, 404: MessageSchema, 500: MessageSchema},
)
async def get_post(request, post_id: int):
    try:
        return (
            await Post.objects.select_related("category")
            .prefetch_related("tags")
            .aget(pk=post_id, status="published")
        )
    except Post.DoesNotExist:
        return 404, {"message": "Not found"}
    except Exception as e:
        logging.error(e)
        return 500, {"message": "Internal Server Error"}


# NOTE:
# must put dynamic routing under static routing
# if add new static router remember to add the name to exclude list manually
# at 'api/constants.py'
@router.get(
    "/{str:post_slug}",
    response={200: PostSchema, 404: MessageSchema, 500: MessageSchema},
)
async def get_post_from_slug(request, post_slug: str):
    try:
        return (
            await Post.objects.select_related("category")
            .prefetch_related("tags")
            .aget(slug=post_slug, status="published")
        )
    except Post.DoesNotExist:
        return 404, {"message": "Not found"}
    except Exception as e:
        logging.error(e)
        return 500, {"message": "Internal Server Error"}
