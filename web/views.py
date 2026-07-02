import random

from django.http import Http404, HttpRequest, HttpResponsePermanentRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.templatetags.static import static
from django.views.decorators.http import require_GET

from api.models import Post


# Create your views here.
@require_GET
def index(request: HttpRequest):
    return render(request, "web/pages/index.html")


@require_GET
def test(request: HttpRequest):
    return render(request, "web/pages/test.html")


@require_GET
def blog(request: HttpRequest):
    posts = Post.objects.filter(status="published")[:10]
    context = {"posts": posts}
    return render(request, "web/pages/blog.html", context)


@require_GET
def blog_random_post(request: HttpRequest):
    published_posts = Post.objects.filter(status="published")
    count = published_posts.count()
    if count == 0:
        return redirect("blog")

    random_index = random.randint(0, count - 1)
    post = published_posts[random_index]
    return redirect("blog_post_slug", post_slug=post.slug)


@require_GET
def blog_post_id(request: HttpRequest, post_id: int):
    post = get_object_or_404(Post, id=post_id)
    return redirect("blog_post_slug", post_slug=post.slug, permanent=True)


@require_GET
def blog_post_slug(request: HttpRequest, post_slug: str):
    post = Post.objects.filter(slug=post_slug).first()
    if post is None or post.status != "published":
        raise Http404("This post not found.")

    context = {
        "title": post.title,
        "content_html": post.content_html,
        "toc": post.toc,
        "layout": post.layout,
        "slug": post.slug,
    }
    return render(request, "web/pages/blog_post.html", context)


@require_GET
def about(request: HttpRequest):
    return render(request, "web/pages/about.html")


# nginx will process this in prod
@require_GET
def favicon(request: HttpRequest):
    return HttpResponsePermanentRedirect(static("favicon.ico"))


def page_not_found(request: HttpRequest, exception: Exception):
    context = {
        "visitor": (
            request.user.get_username() if request.user.is_authenticated else "visitor"
        )
    }
    return render(request, "404.html", context=context, status=404)


def server_error(request: HttpRequest):
    return render(request, "500.html", status=500)
