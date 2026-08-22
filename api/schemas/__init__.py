"""API schemas package.

This package contains all Pydantic/Ninja schemas for the API.
Schemas are organized by domain for better maintainability.
"""

# Anime schemas
from .anime import (
    AnimeId,
    AnimeIds,
    AnimeSchema,
)
from .auth import OAuthProviderSchema, OAuthSessionSchema

# Base schemas
from .base import (
    CategorySchema,
    ClientIdSchema,
    IdSchema,
    IdsSchema,
    MessageSchema,
    PaginationSchema,
    TagsSchema,
)

# Category schemas
from .category import CategoryResponseSchema

# Comment schemas
from .comment import (
    CommentIdsSchema,
    CommentPaginationResponse,
    CommentResponse,
    CommentSchema,
    NewCommentMetadataSchema,
    NewCommentSchema,
)

# Gal (Visual Novel) schemas
from .gal import (
    GalPaginationResponse,
    GalSchema,
    GalUpdateSchema,
)

# Image
from .image import ImageUploadRequestSchema, ImageUploadResponseSchema

# Markdown
from .markdown import MarkdownRenderRequest, MarkdownRenderResponse

# Post schemas
from .post import (
    PostCardSchema,
    PostCardsSchema,
    PostCardsWithSimilaritySchema,
    PostCardWithSimilarity,
    PostRenderedSchema,
    PostSchema,
)

# Sitemap schemas
from .sitemap import PostIdsForSitemap, PostSitemapSchema

# System and health check schemas
from .system import (
    ApiStatusSchema,
    DatabaseStatusSchema,
    SystemInfoSchema,
)

__all__ = [
    # Base
    "PaginationSchema",
    "MessageSchema",
    "IdSchema",
    "IdsSchema",
    # Auth
    "ClientIdSchema",
    "OAuthProviderSchema",
    "OAuthSessionSchema",
    # Category & Tags
    "CategorySchema",
    "TagsSchema",
    # Comments
    "CommentSchema",
    "CommentPaginationResponse",
    "CommentResponse",
    "CommentIdsSchema",
    "NewCommentMetadataSchema",
    "NewCommentSchema",
    # Posts
    "PostSchema",
    "PostCardSchema",
    "PostCardsSchema",
    "CategoryResponseSchema",
    "PostRenderedSchema",
    "PostCardWithSimilarity",
    "PostCardsWithSimilaritySchema",
    # Sitemap
    "PostSitemapSchema",
    "PostIdsForSitemap",
    # Gal
    "GalSchema",
    "GalPaginationResponse",
    "GalUpdateSchema",
    # Image
    "ImageUploadRequestSchema",
    "ImageUploadResponseSchema",
    # Anime
    "AnimeId",
    "AnimeIds",
    "AnimeSchema",
    # System
    "SystemInfoSchema",
    "DatabaseStatusSchema",
    "ApiStatusSchema",
    # markdown
    "MarkdownRenderRequest",
    "MarkdownRenderResponse",
]
