from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from api.models import Post


class StaticViewSitemap(Sitemap):
    changefreq = "daily"
    priority = 0.5

    def items(self):
        return ["index", "blog", "about"]

    def location(self, item: str):
        return reverse(item)


class PostSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.8

    def items(self):
        return Post.objects.filter(status="published").order_by(
            "-published_at", "-created_at"
        )

    def lastmod(self, obj: Post):
        return obj.content_update_at or obj.created_at

    def location(self, item: Post):
        return reverse("blog_post_slug", args=[item.slug])
