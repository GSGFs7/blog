from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVector, SearchVectorField
from django.core.exceptions import ValidationError
from django.db import models, transaction
from pgvector.django import HnswIndex, VectorField

from api.constants import POST_RESERVED_SLUGS
from api.utils import chinese_slugify, extract_metadata

from .base import BaseModel
from .category import Category
from .tag import Tag


class Post(BaseModel):
    # 基础信息
    title = models.CharField(
        max_length=50, unique=True, db_index=True, null=False, blank=True
    )
    content = models.TextField(blank=False, null=False, help_text="文章正文, 必填")

    # 渲染后的内容
    content_html = models.TextField(null=True, blank=True, help_text="自动生成")
    toc = models.JSONField(null=True, blank=True, help_text="文章目录")

    # 图片相关
    cover_image = models.URLField(
        max_length=500, blank=True, null=True, help_text="文章封面图片(URL)"
    )
    header_image = models.URLField(
        max_length=500, blank=True, null=True, help_text="文章og显示图片(URL)"
    )  # The only purpose now is as og image in website metadata

    # SEO相关
    slug = models.SlugField(
        max_length=100,
        unique=True,
        blank=True,
        help_text="url 地址 (暂时没用)",
        db_index=True,
    )
    meta_description = models.CharField(
        max_length=160,
        blank=True,
        help_text="SEO描述",
    )
    keywords = models.CharField(
        max_length=200, blank=True, help_text="文章关键词，用逗号分隔"
    )

    # 统计
    view_count = models.PositiveIntegerField(default=0, help_text="(暂时没用)")

    # 排序
    order = models.IntegerField(
        default=0, help_text="是否覆盖默认的优先级, 数值越大越靠前"
    )

    # 查询相关
    tags = models.ManyToManyField(
        Tag,
        blank=True,
        # null=True, 本来就可以为空
        default=None,
        related_name="posts",
    )  # tags 可以对多

    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        blank=True,  # 在表单中可以为空
        null=True,  # 在数据库中可以为空
        default=None,
        related_name="posts",
    )  # 只能有一个 禁止删除还有文章的分类

    # 文章状态
    status = models.CharField(
        max_length=20,
        # https://docs.djangoproject.com/zh-hans/5.1/ref/models/fields/#choices
        # 强制执行模型验证 需要提供映射关系 第一个是存储的实际值 第二个是人类可读的名称
        choices=[("draft", "草稿"), ("published", "已发布")],
        default="draft",
    )

    # 向量化搜索已迁移至 PostChunk
    # embedding = VectorField(dimensions=768, null=True, blank=True)

    # PG full-text search
    pg_gin_search_vector = SearchVectorField(null=True, blank=True)
    tokenized_content = models.TextField(blank=True, null=True)

    # update in 'api/signals.py'
    content_update_at = models.DateTimeField(
        null=False, blank=True, help_text="文章正文最后更新时间"
    )

    class Meta(BaseModel.Meta):
        ordering = ["-order", "-created_at"]
        indexes = [
            GinIndex(fields=["pg_gin_search_vector"]),
        ]

    def __str__(self):
        return self.title

    # rewrite save action
    # called after adminFrom (at `./admin.py`)
    @transaction.atomic  # keep atomic, all success or all failures
    def save(self, *args, **kwargs):
        post_metadata = extract_metadata(self.content)

        # === title ===
        if not self.title:
            self.title = post_metadata.get("title") or ""

        # === slug ===
        if not self.slug:
            self.slug = post_metadata.get("slug")
        if not self.slug and self.title:
            self.slug = chinese_slugify(self.title)
        if self.slug in POST_RESERVED_SLUGS:
            raise ValidationError(
                f"Slug '{self.slug}' is a reserved keyword and cannot be used."
            )

        # === description ===
        if not self.meta_description:
            self.meta_description = post_metadata.get("description")

        # === keywords ===
        if not self.keywords:
            self.keywords = post_metadata.get("keywords")

        # === image ===
        if not self.cover_image:
            self.cover_image = post_metadata.get("cover_image")
        if not self.header_image:
            self.header_image = post_metadata.get("header_image")

        # === category ===
        if not self.category and post_metadata.get("category"):
            category = post_metadata.get("category")
            category, created = Category.objects.get_or_create(name=category)
            self.category = category

        # === tokenize (PG FTS) ===
        import jieba

        self.tokenized_content = " ".join(jieba.lcut(self.content, cut_all=True))

        # === vector ===
        # Moved to Celery task (see api/tasks.py: generate_post_embedding)
        # The embedding will be generated asynchronously after the post is saved

        # save main object, all settings above will be saved
        # after that, continue to process operations that require primary keys
        super().save(*args, **kwargs)

        # === tags ===
        # NOTE: This logic is already handled in PostAdminForm.clean()
        # However, it's kept here to support non-Admin post creation (e.g. scripts, API)
        # This is safe as it checks `if not self.tags.exists()` before processing
        if not self.tags.exists():  # must use `.exists()` to check it
            tags_to_set = []
            tag_list = post_metadata["tags"]
            for tag_name in tag_list:
                tag_obj, created = Tag.objects.get_or_create(name=tag_name)
                tags_to_set.append(tag_obj)
            self.tags.set(tags_to_set)

        # === Full-text search ===
        # generate PG full-text search vector
        Post.objects.filter(pk=self.pk).update(
            pg_gin_search_vector=SearchVector(
                "title",
                "tokenized_content",
                config="simple",
            )
        )


class PostChunk(BaseModel):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="chunks")
    content = models.TextField()
    embedding = VectorField(dimensions=768)
    chunk_index = models.IntegerField()  # The order of the block in the original text

    class Meta:
        indexes = [
            HnswIndex(
                name="post_chunk_embedding_idx",
                fields=["embedding"],
                m=32,
                ef_construction=256,
                opclasses=["vector_cosine_ops"],
            )
        ]
