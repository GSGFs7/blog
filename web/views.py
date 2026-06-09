from django.http import HttpRequest
from django.shortcuts import get_object_or_404, render

from api.models import Post


# Create your views here.
def index(request: HttpRequest):
    return render(request, "web/pages/index.html")


def test(request: HttpRequest):
    return render(request, "web/pages/test.html")


def blog(request: HttpRequest):
    posts = Post.objects.all()[:10]
    context = {"posts": posts}
    return render(request, "web/pages/blog.html", context)


def blog_post(request: HttpRequest, post_id: int):
    post = get_object_or_404(Post, id=post_id)
    context = {
        "title": post.title,
        "content_html": post.content_html,
        "toc": post.toc,
        "layout": post.layout,
    }
    return render(request, "web/pages/blog_post.html", context)


def about(request: HttpRequest):
    return render(request, "web/pages/about.html")
