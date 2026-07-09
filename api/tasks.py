import logging

from celery import shared_task
from django.core.mail import mail_admins
from django.db import transaction
from django.utils import timezone

from .ml_model import get_ml_model
from .models import Gal, Post, PostChunk
from .text_chunking import chunk_text
from .vndb import query_vn

logger = logging.getLogger(__name__)


UPDATE_VNDB_INTERVAL: int = 60 * 60 * 24 * 7  # Updated every 7 days


# TODO: updated field configable
@shared_task
def sync_vndb_data():
    """
    Celery task to synchronize VNDB data.
    """
    logger.info("开始同步 VNDB 数据...")
    entries = Gal.objects.all()
    current_time = timezone.now().timestamp()

    for entry in entries:
        if current_time - entry.updated_at.timestamp() < UPDATE_VNDB_INTERVAL:
            logger.info(f"跳过最近已更新: {entry.vndb_id}")
            continue

        try:
            data = query_vn(entry.vndb_id)

            if "results" in data and data["results"]:
                vn_data = data["results"][0]
                # alt_title = vn_data.get("alttitle", None)
                # if alt_title and isinstance(alt_title, str) and alt_title.strip():
                #     entry.title = alt_title
                # else:
                #     entry.title = vn_data["title"]
                # title_cn = None
                # for title in vn_data.get("titles", []):
                #     if title["lang"] == "zh-Hans":
                #         title_cn = title["title"]
                #         break
                # entry.title_cn = title_cn
                # entry.cover_image = vn_data["image"]["url"]
                entry.vndb_rating = vn_data.get("rating", None)  # rating only

                entry.save()
            else:
                logger.warning(f"未找到 VNDB 数据: {entry.vndb_id}")
                continue
        except Exception as e:
            logger.error(f"查询 VNDB 数据失败: {entry.vndb_id}, 错误: {e}")
            continue
    logger.info("VNDB 数据同步完成。")


@shared_task
def mail_admins_task(subject: str, message: str):
    try:
        mail_admins(subject, message)
        logging.info("Success mail admin")
    except Exception as e:
        logging.warning(f"Mail admin failed: {e}")


@shared_task
@transaction.atomic
def generate_post_chunks_embedding_task(post_id: int):
    post = Post.objects.get(id=post_id)

    # clean old chunk
    post.chunks.all().delete()

    text_chunks = chunk_text(post.content)

    if not text_chunks:
        return

    model = get_ml_model()
    vectors = model.embed_documents(text_chunks)

    new_chunks = []
    for i, (content, vector) in enumerate(zip(text_chunks, vectors, strict=True)):
        new_chunks.append(
            PostChunk(
                post=post,
                content=content,
                embedding=vector,
                chunk_index=i,
            )
        )

    PostChunk.objects.bulk_create(new_chunks)


@shared_task
def generate_search_embedding_task(query: str):
    """
    Celery task to generate embedding for search query.
    """
    try:
        model = get_ml_model()
        return model.embed_query(query)
    except Exception as e:
        logger.error(f"生成搜索 embedding 失败: {query[:50]}, 错误: {e}")
        raise
