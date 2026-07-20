from django.core.paginator import AsyncPaginator
from django.http import HttpRequest, HttpResponse, HttpResponsePermanentRedirect
from django.shortcuts import aget_object_or_404, redirect, render
from django.template.response import TemplateResponse
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
async def blog(request: HttpRequest):
    page = request.GET.get("page", "1")
    page = max(1, int(page)) if page.isdigit() else 1

    all_posts = (
        Post.objects.filter(status="published")
        .select_related("category")
        .prefetch_related("tags")
    )
    paginator = AsyncPaginator(all_posts, 10)
    page_obj = await paginator.aget_page(page)

    page_number = page_obj.number
    post_list = await page_obj.aget_object_list()
    has_previous = await page_obj.ahas_previous()
    has_next = await page_obj.ahas_next()
    previous_page_number = (
        await page_obj.aprevious_page_number() if has_previous else None
    )
    next_page_number = await page_obj.anext_page_number() if has_next else None
    context = {
        "page_number": page_number,
        "post_list": post_list,
        "has_previous": has_previous,
        "has_next": has_next,
        "previous_page_number": previous_page_number,
        "next_page_number": next_page_number,
    }
    return TemplateResponse(request, "web/pages/blog.html", context=context)


@require_GET
async def blog_random_post(request: HttpRequest):
    # faster, but code more complex
    # ```py
    # published_posts = Post.objects.filter(status="published")
    # count = await published_posts.acount()
    # random_index = random.randint(0, count - 1)
    # post = await published_posts.only("slug")[
    #     random_index : random_index + 1
    # ].afirst()
    # ```

    # use Postgres random choice
    # poor performance when record exceed 10k (it will sacn every raw in the table)
    # I mean, it just a personal blog
    # even if you write it every day, it enough uses 27 years
    post = (
        await Post.objects.filter(status="published")
        .only("slug")
        .order_by("?")
        .afirst()
    )
    if post is None:
        return redirect("blog")

    return redirect("blog_post_slug", post_slug=post.slug)


@require_GET
async def blog_post_id(request: HttpRequest, post_id: int):
    post = await aget_object_or_404(Post, id=post_id)
    return redirect("blog_post_slug", post_slug=post.slug, permanent=True)


@require_GET
async def blog_post_slug(request: HttpRequest, post_slug: str):
    post = await aget_object_or_404(Post, slug=post_slug, status="published")

    context = {
        "title": post.title,
        "content_html": post.content_html,
        "toc": post.toc,
        "layout": post.layout,
        "slug": post.slug,
    }
    return TemplateResponse(request, "web/pages/blog_post.html", context=context)


@require_GET
async def blog_post_markdown(request: HttpRequest, post_slug: str):
    post = await aget_object_or_404(
        Post.objects.only("slug", "content"),
        slug=post_slug,
        status="published",
    )
    response = HttpResponse(
        post.content,
        content_type="text/markdown; charset=utf-8",
    )
    response["Content-Disposition"] = f'inline; filename="{post.slug}.md"'
    return response


@require_GET
def about(request: HttpRequest):
    return render(request, "web/pages/about.html")


@require_GET
def entertainment(request: HttpRequest):
    return render(request, "web/pages/entertainment.html")


@require_GET
def login(request: HttpRequest):
    return render(request, "web/pages/login.html")


@require_GET
def user(request: HttpRequest):
    return render(request, "web/pages/user.html")


@require_GET
def privacy(request: HttpRequest):
    return render(request, "web/pages/privacy.html")


# nginx will process this in prod
@require_GET
def favicon(request: HttpRequest):
    return HttpResponsePermanentRedirect(static("favicon.ico"))


# sync only
def page_not_found(request: HttpRequest, exception: Exception):
    user = getattr(request, "user", None)
    visitor = (
        user.get_username() if user is not None and user.is_authenticated else "visitor"
    )
    context = {"visitor": visitor}
    return TemplateResponse(request, "404.html", context=context, status=404)


def server_error(request: HttpRequest):
    return render(request, "500.html", status=500)
