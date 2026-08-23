import logging

from django.db import transaction
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone

from .markdown import Markdown
from .models import Anime, Gal, Post

logger = logging.getLogger(__name__)


@receiver(pre_save, sender=Gal)
def sync_with_vndb(sender, instance, **kwargs):
    from .vndb import query_vn

    def find_cn_title(titles):
        for title in titles:
            if title["lang"] == "zh-Hans":
                return title["title"]
        return None

    if not instance.vndb_id:
        return

    if not instance.pk or not instance.title:
        try:
            # circular import, must use signals to avoid
            res = query_vn(instance.vndb_id)
            if not res["results"]:
                return

            vn_data = res["results"][0]

            # Update the instance not the database directly
            # "{"alttitle": null, "title": "xxx"}" -> return None
            # instance.title = vn_data.get("alttitle", vn_data["title"])
            instance.title = vn_data.get("alttitle") or vn_data["title"]
            instance.title_cn = find_cn_title(vn_data.get("titles", []))
            instance.cover_image = vn_data["image"]["url"]
            instance.vndb_rating = vn_data.get("rating", None)
            # This is a pre_save signal, should not call `save()`
            # here otherwise it will cause infinite loop
        except Exception as e:
            logger.error(f"Failed to sync VNDB data({instance.vndb_id}): {e}")


@receiver(pre_save, sender=Anime)
def sync_with_jikan(sender, instance, **kwargs):
    from .jikan import query_anime

    if not instance.mal_id:
        return

    if not instance.pk or not instance.title:
        try:
            res = query_anime(instance.mal_id)

            title = None
            for t in res.titles:
                if t.type == "Japanese":
                    title = t.title
            if title is None:
                title = res.titles[0].title

            instance.name = title
            instance.year = res.year
            instance.synopsis = res.synopsis
            instance.cover_image = res.images.webp.large_image_url
            instance.rating = res.rating
        except Exception as e:
            logger.error(f"Failed to update Anime data({instance.mal_id}): {e}")


@receiver(post_save, sender=Gal)
def convert_gal_markdown_to_html(sender, instance, **kwargs):
    try:
        html = Markdown().render(instance.review)
        instance.review_html = html
        Gal.objects.filter(pk=instance.pk).update(review_html=html)
    except Exception as e:
        logger.error(f"Markdown conversion failed: {e}")


@receiver(post_save, sender=Post)
def convert_post_markdown_to_html(sender, instance, **kwargs):
    try:
        html, toc = Markdown().render_with_toc(instance.content)

        instance.content_html = html
        instance.toc = toc
        Post.objects.filter(pk=instance.pk).update(content_html=html, toc=toc)
    except Exception as e:
        logger.error(f"Markdown conversion failed: {e}")


@receiver(pre_save, sender=Post)
def update_content_update_at(sender, instance, **kwargs):
    if instance.pk:
        try:
            old_instance = Post.objects.get(pk=instance.pk)
            # content update
            if old_instance.content != instance.content:
                instance.content_update_at = timezone.now()
            # 'content_update_at' not set
            if instance.content_update_at is None:
                instance.content_update_at = timezone.now()
        except Post.DoesNotExist:
            instance.content_update_at = timezone.now()
    else:
        instance.content_update_at = timezone.now()


@receiver(post_save, sender=Post)
def generate_post_embedding_async(sender, instance, created, **kwargs):
    from .tasks import generate_post_chunks_embedding_task

    """
    Trigger Celery task to generate embedding for post asynchronously.
    This runs after the post is saved to the database.
    Uses transaction.on_commit to ensure the task runs after the transaction commits.
    """
    try:

        def task():
            generate_post_chunks_embedding_task.delay(instance.pk)
            logger.info(
                f"Triggered chunk embedding generate task, post ID {instance.pk}"
            )

        transaction.on_commit(task)
    except Exception as e:
        logger.error(
            f"Failed trigger embedding generate task, post ID {instance.pk}: {e}"
        )
