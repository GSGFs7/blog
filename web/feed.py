from django.contrib.syndication.views import Feed
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.feedgenerator import Atom1Feed

from api.models import Post


class Atom1FeedWithContent(Atom1Feed):
    def add_root_elements(self, handler):
        super().add_root_elements(handler)
        handler.addQuickElement("subtitle", "GSGFs's blog")
        handler.addQuickElement("icon", "https://gsgfs.moe/favicon.ico")
        handler.addQuickElement("logo", "https://gsgfs.moe/favicon.ico")
        handler.addQuickElement(
            "link",
            "",
            {"rel": "license", "href": "https://creativecommons.org/licenses/by/4.0/"},
        )

    def add_item_elements(self, handler, item):
        super().add_item_elements(handler, item)
        if item.get("content"):
            handler.addQuickElement("content", item["content"], {"type": "html"})


class BlogPostFeed(Feed):
    feed_type = Atom1FeedWithContent

    title = "GSGFs's blog"
    link = "/blog"
    feed_url = reverse_lazy("blog_feed")
    # RFC 4151
    feed_guid = "tag:gsgfs.moe,2024:blog"
    description = "GSGFs's blog"
    categories = ["技术", "生活"]
    language = "zh-Hans"

    author_name = "GSGFs"
    author_link = "https://gsgfs.moe"

    def feed_copyright(self):
        return (
            f"Copyright (c) 2024 - {timezone.now().year} GSGFs. "
            "Licensed under CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/)."
        )

    def items(self):
        return (
            Post.objects.filter(status="published")
            .select_related("category")
            .prefetch_related("tags")
            .order_by("-published_at", "-created_at")[:10]
        )

    def item_title(self, item: Post):
        return item.title

    def item_description(self, item: Post):
        return item.meta_description

    def item_link(self, item: Post):
        return reverse("blog_post_slug", args=[item.slug])

    def item_pubdate(self, item: Post):
        return item.published_at or item.created_at

    def item_updateddate(self, item: Post):
        return item.content_update_at

    def item_categories(self, item: Post):
        categories = [t.name for t in item.tags.all()]
        if item.category and item.category.name not in categories:
            categories.append(item.category.name)
        return categories

    def item_guid(self, item: Post):
        return f"tag:gsgfs.moe,{item.created_at:%Y-%m-%d}:blog#post-{item.pk}"

    def item_extra_kwargs(self, item: Post):
        return {"content": item.content_html or item.content}


# doc: https://docs.djangoproject.com/zh-hans/6.0/ref/contrib/syndication/
