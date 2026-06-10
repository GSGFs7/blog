from django import forms
from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.forms.models import ModelForm
from django.http import HttpRequest
from django.utils import timezone

from api.constants import POST_RESERVED_SLUGS
from api.models import (
    Anime,
    ApiClient,
    Comment,
    Gal,
    Guest,
    Post,
    Tag,
)
from api.utils import chinese_slugify, extract_metadata


class PostAdminForm(forms.ModelForm):
    class Meta:
        model = Post
        fields = "__all__"

    def clean(self):
        """
        Cleans and validates form data for a Post model.

        - Extracts metadata from the 'content' field using front matter if available.
        - If 'title' is missing, attempts to extract it from metadata;
         checks for uniqueness.
        - Automatically generates 'slug' from metadata or the title if not provided.
        - Collects validation errors for missing or duplicate fields and raises
         ValidationError if any are found.

        Returns:
            dict: The cleaned and possibly modified form data.

        Raises:
            ValidationError: If required fields are missing, cannot be
            extracted/generated, or if the title is not unique.
        """

        cleaned_data = super().clean()
        title: str | None = cleaned_data.get("title")
        content: str | None = cleaned_data.get("content")

        metadata = {}
        errors = {}

        # === content ===
        if content:
            metadata = extract_metadata(content)
        else:
            errors["content"] = "Content field cannot be empty."

        # === tags ===
        if not cleaned_data.get("tags"):
            tag_names: str | None = metadata.get("tags")
            if tag_names:
                tags_to_set = []
                for tag_name in tag_names:
                    tag_obj, _ = Tag.objects.get_or_create(name=tag_name)
                    tags_to_set.append(tag_obj)
                cleaned_data["tags"] = tags_to_set

        # === title ===
        if not title:
            extracted_title = metadata.get("title")
            if extracted_title:
                cleaned_data["title"] = extracted_title
                if (
                    Post.objects.filter(title=extracted_title)
                    .exclude(pk=self.instance.pk)
                    .exists()
                ):
                    errors["title"] = (
                        "The title extracted from Front Matter already exists."
                    )
            else:
                errors["title"] = (
                    "The title field cannot be empty and cannot be "
                    "automatically extracted from Front Matter."
                )

        # === slug ===
        if not cleaned_data.get("slug"):
            cleaned_data["slug"] = metadata.get("slug") or chinese_slugify(
                str(cleaned_data.get("title", ""))
            )
            if not cleaned_data.get("slug"):
                errors["slug"] = (
                    "Slug field cannot be empty and cannot be automatically generated."
                )
            if (
                Post.objects.filter(slug=cleaned_data.get("slug"))
                .exclude(pk=self.instance.pk)
                .exists()
            ):
                errors["slug"] = "The slug already exists."
        if cleaned_data.get("slug") in POST_RESERVED_SLUGS:
            errors["slug"] = (
                "Slug is reserved and cannot be used. Please choose another."
            )

        if errors:
            raise ValidationError(errors)

        return cleaned_data


class PostAdmin(admin.ModelAdmin):
    fieldsets = [
        (
            None,
            {
                "fields": [
                    "title",
                    "content",
                    "content_html",
                    "layout",
                    "toc",
                    "tags",
                    "category",
                    "status",
                ]
            },
        ),
        (
            "Meta data",
            {
                "fields": [
                    "cover_image",
                    "header_image",
                    "slug",
                    "meta_description",
                    "view_count",
                    "order",
                    "keywords",
                    "content_update_at",
                ]
            },
        ),
    ]

    @admin.action(description="重新生成所选文章的所有生成内容")
    def regenerate_content(self, request, queryset):
        for post in queryset:
            post.save()
        self.message_user(request, f"已重新生成 {queryset.count()} 篇文章的内容")

    actions = [regenerate_content]
    form = PostAdminForm
    readonly_fields = ["updated_at", "content_update_at"]
    list_display = [
        "title",
        "status",
        "created_at",
        "updated_at",
    ]  # 在列表中显示日期
    list_filter = ["status", "category"]  # 添加过滤器
    search_fields = ["title", "content"]  # 添加搜索功能


class CommentAdmin(admin.ModelAdmin):
    fieldsets = [
        (
            None,
            {
                "fields": [
                    "content",
                    "post",
                    "guest",
                    "user_agent",
                    "OS",
                    "platform",
                    "browser",
                    "browser_version",
                ]
            },
        ),
        (
            "Time Information",
            {
                "fields": [
                    "created_at",
                    "updated_at",
                ]
            },
        ),
    ]

    readonly_fields = ["created_at", "updated_at"]
    list_display = ["content", "post", "guest", "created_at", "updated_at"]


class GalAdmin(admin.ModelAdmin):
    fieldsets = [
        (
            None,
            {
                "fields": [
                    "vndb_id",
                    "title",
                    "title_cn",
                    # score
                    "character_score",
                    "story_score",
                    "comprehensive_score",
                    "vndb_rating",
                    # review
                    "summary",
                    "review",
                    "review_html",
                    "cover_image",
                ]
            },
        ),
        (
            "Time Information",
            {
                "fields": [
                    "created_at",
                    "updated_at",
                ]
            },
        ),
    ]

    readonly_fields = ["created_at", "updated_at"]
    list_display = ["vndb_id", "title", "created_at", "updated_at"]


class GuestAdmin(admin.ModelAdmin):
    fieldsets = [
        (
            None,
            {
                "fields": [
                    "name",
                    "unique_id",
                    "email",
                    "password",
                    "provider",
                    "provider_id",
                    "avatar",
                    "is_admin",
                ]
            },
        ),
        (
            "Time Information",
            {
                "fields": [
                    "created_at",
                    "updated_at",
                    "last_visit",
                ]
            },
        ),
    ]

    readonly_fields = ["created_at", "updated_at", "last_visit"]
    list_display = ["name", "provider", "created_at", "updated_at"]
    list_filter = ["provider"]


class AnimeAdmin(admin.ModelAdmin):
    fieldsets = [
        (
            None,
            {
                "fields": [
                    "mal_id",
                    "name",
                    "name_cn",
                    "year",
                    "synopsis",
                    "cover_image",
                    "rating",
                    "score",
                    "review",
                ]
            },
        ),
        (
            "Time Information",
            {
                "fields": [
                    "created_at",
                    "updated_at",
                ]
            },
        ),
    ]

    readonly_fields = ["created_at", "updated_at"]
    list_display = ["name", "created_at", "updated_at"]


class ApiClientAdmin(admin.ModelAdmin):
    list_display = [
        "client_id",
        "display_is_active",
        "expires_at",
        "revoked_at",
        "created_at",
    ]
    list_filter = []
    search_fields = ["client_id"]
    readonly_fields = [
        "created_at",
        "updated_at",
        "masked_secret",
        "revoked_at",
    ]

    _add_fieldsets = [
        (None, {"fields": ["client_id", "scopes"]}),
        ("Lifecycle", {"fields": ["expires_at"]}),
    ]
    _change_fieldsets = [
        (None, {"fields": ["client_id", "masked_secret", "scopes"]}),
        ("Lifecycle", {"fields": ["expires_at", "revoked_at"]}),
        ("Timestamps", {"fields": ["created_at", "updated_at"]}),
    ]

    # makesure it display as a boolean (it will render a icon in Django Admin panel)
    @admin.display(boolean=True, description="Active")
    def display_is_active(self, obj):
        return obj.is_active

    # do not display raw secret
    @admin.display(description="Secret")
    def masked_secret(self, obj):
        raw = obj.secret
        if not raw:
            return "-"
        return f"******{raw[-4:]}"

    def get_fieldsets(self, request, obj=None):
        if obj is None:
            return self._add_fieldsets
        return self._change_fieldsets

    def get_readonly_fields(self, request, obj=None):
        if obj is None:
            return []
        return self.readonly_fields

    def save_model(
        self, request: HttpRequest, obj: ApiClient, form: ModelForm, change: bool
    ):
        if not change:
            raw_secret = ApiClient.generate_secret()
            obj.secret = raw_secret
            super().save_model(request, obj, form, change)
            self.message_user(
                request,
                f"“{obj.client_id}”的 secret （只会显示一次）: {raw_secret}",
                level=messages.SUCCESS,
            )
        else:
            super().save_model(request, obj, form, change)

    actions = ["regenerate_secret", "revoke_clients"]

    @admin.action(description="Revoke selected clients")
    def revoke_clients(self, request, queryset):
        now = timezone.now()
        active = queryset.filter(revoked_at__isnull=True)
        count = active.update(revoked_at=now)
        skipped = queryset.count() - count
        msg = f"已撤销 {count} 个客户端。"
        if skipped:
            msg += f" {skipped} 个已处于撤销状态，跳过。"
        self.message_user(request, msg, level=messages.SUCCESS)

    @admin.action(description="Regenerate secret for selected clients")
    def regenerate_secret(self, request, queryset):
        results = []
        skipped = 0
        for client in queryset:
            if client.revoked_at is not None:
                skipped += 1
                continue
            raw_secret = ApiClient.generate_secret()
            client.secret = raw_secret
            client.save(update_fields=["secret"])
            results.append(f"  {client.client_id}: {raw_secret}")

        msg = f"已重新生成 {len(results)} 个 secret（只会显示一次）:\n" + "\n".join(
            results
        )
        if skipped:
            msg += f"\n跳过 {skipped} 个已撤销的客户端。"
        self.message_user(request, msg, level=messages.SUCCESS)


admin.site.register(Post, PostAdmin)
admin.site.register(Guest, GuestAdmin)
admin.site.register(Comment, CommentAdmin)
admin.site.register(Gal, GalAdmin)
admin.site.register(Anime, AnimeAdmin)
admin.site.register(ApiClient, ApiClientAdmin)
