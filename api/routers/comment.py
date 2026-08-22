import logging

from ninja import Router, Status

from api.auth import AsyncTimeBaseAuth
from api.models import Comment, OAuthIdentity, Post
from api.schemas import (
    CommentIdsSchema,
    CommentResponse,
    CommentSchema,
    IdSchema,
    MessageSchema,
    NewCommentSchema,
)
from api.tasks import mail_admins_task

router = Router()
logger = logging.getLogger(__name__)


# get comment from id
@router.get(
    "/{int:comment_id}",
    response={200: CommentSchema, 404: MessageSchema, 500: MessageSchema},
)
async def get_comment(request, comment_id: int):
    try:
        return await Comment.objects.select_related("guest").aget(pk=comment_id)
    except Comment.DoesNotExist:
        return Status(404, {"message": "Not found"})
    except Exception as e:
        logger.error(e)
        return Status(500, {"message": "Internal Server Error"})


# get comment ids from post id
@router.get(
    "/post/{int:post_id}/ids",
    response={200: CommentIdsSchema, 404: MessageSchema, 500: MessageSchema},
)
async def get_comment_ids_from_post(request, post_id: int):
    try:
        if not await Post.objects.filter(pk=post_id).aexists():
            return Status(404, {"message": "Post not found"})
        comment_ids = [
            i
            async for i in Comment.objects.filter(post_id=post_id).values_list(
                "id", flat=True
            )
        ]
        return Status(200, {"ids": comment_ids})
    except Exception as e:
        logger.error(e)
        return Status(500, {"message": "Internal Server Error"})


# get all comment with content
@router.get(
    "/post/{int:post_id}",
    response={200: CommentResponse, 404: MessageSchema, 500: MessageSchema},
)
@router.get(
    "/post/{int:post_id}/all",
    response={200: CommentResponse, 404: MessageSchema, 500: MessageSchema},
)
async def get_all_comment_from_post(request, post_id: int):
    try:
        if not await Post.objects.filter(pk=post_id).aexists():
            return Status(404, {"message": "Post not found"})

        comments = [
            post_comment
            async for post_comment in Comment.objects.select_related("guest").filter(
                post_id=post_id
            )
        ]
        return Status(200, {"comments": comments})
    except Exception as e:
        logger.error(e)
        return Status(500, {"message": "Internal Server Error"})


@router.post(
    "/new",
    response={200: IdSchema, 404: MessageSchema, 500: MessageSchema},
    auth=AsyncTimeBaseAuth(),
)
async def new_comment(request, body: NewCommentSchema):
    try:
        post = await Post.objects.aget(pk=body.post_id)
        identity = await OAuthIdentity.objects.select_related("guest").aget(
            provider__provider_key=body.provider_key,
            user_id=body.user_id,
        )

        comment = await Comment.objects.acreate(
            content=body.content, post=post, guest=identity.guest
        )
        if body.metadata is not None:
            comment.OS = body.metadata.OS
            comment.user_agent = body.metadata.user_agent
            comment.browser = body.metadata.browser
            comment.browser_version = body.metadata.browser_version
            comment.platform = body.metadata.platform
            await comment.asave()

        # tall admin had a new comment
        mail_admins_task.delay(
            "had a new comment", f"had a new comment in post '{post.title}'"
        )

        return Status(200, {"id": comment.pk})  # pk = id
    except Post.DoesNotExist:
        return Status(404, {"message": "Post not found"})
    except OAuthIdentity.DoesNotExist:
        return Status(404, {"message": "Guest not found"})
    except Exception as e:
        logger.error(e)
        return Status(500, {"message": "Internal Server Error"})
