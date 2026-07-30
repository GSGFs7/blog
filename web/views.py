from django.core.paginator import AsyncPaginator
from django.http import HttpRequest, HttpResponse, HttpResponsePermanentRedirect
from django.http.response import Http404
from django.shortcuts import aget_object_or_404, redirect, render
from django.template.response import TemplateResponse
from django.templatetags.static import static
from django.views.decorators.http import require_GET, require_safe

from api.models import Post
from web.cache import private_page_response, public_page_response


# Create your views here.
@require_safe
def index(request: HttpRequest):
    return public_page_response(
        render(request, "web/pages/index.html"),
        edge_max_age=300,
        max_stale=86400,
    )


@require_GET
def test(request: HttpRequest):
    return private_page_response(render(request, "web/pages/test.html"))


@require_safe
async def blog(request: HttpRequest):
    # page
    page = request.GET.get("page", "1")
    page = max(1, int(page)) if page.isdigit() else 1

    # get paginated obj
    all_posts = (
        Post.objects.filter(status="published")
        .select_related("category")
        .prefetch_related("tags")
    )
    paginator = AsyncPaginator(all_posts, 10)
    page_obj = await paginator.aget_page(page)

    # generate context
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

    response = TemplateResponse(
        request,
        "web/pages/blog.html",
        context=context,
    )
    return public_page_response(
        response,
        edge_max_age=300,
        max_stale=86400,
    )


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
        return private_page_response(redirect("blog"))

    return private_page_response(redirect("blog_post_slug", post_slug=post.slug))


async def blog_latest(request: HttpRequest):
    try:
        post = await Post.objects.filter(status="published").alatest()
    except Post.DoesNotExist:
        return Http404()

    response = redirect("blog_post_slug", post_slug=post.slug)
    return response


@require_GET
async def blog_post_id(request: HttpRequest, post_id: int):
    post = await aget_object_or_404(Post, id=post_id)
    return private_page_response(
        redirect("blog_post_slug", post_slug=post.slug, permanent=True)
    )


@require_safe
async def blog_post_slug(request: HttpRequest, post_slug: str):
    post = await aget_object_or_404(
        Post.objects.select_related("category").prefetch_related("tags"),
        slug=post_slug,
        status="published",
    )

    context = {
        "title": post.title,
        "content_html": post.content_html,
        "toc": post.toc,
        "layout": post.layout,
        "slug": post.slug,
        "meta_description": post.meta_description,
        "keywords": post.keywords,
        "og_image": post.header_image or post.cover_image or "",
        "published_at": post.published_at,
        "content_update_at": post.content_update_at,
        "category_name": post.category.name if post.category_id else "",
        "tag_names": [t.name for t in post.tags.all()],
    }
    response = TemplateResponse(
        request,
        "web/pages/blog_post.html",
        context=context,
    )
    return public_page_response(
        response,
        edge_max_age=300,
        max_stale=86400,
    )


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


@require_safe
def about(request: HttpRequest):
    response = render(request, "web/pages/about.html")
    return public_page_response(
        response,
        edge_max_age=300,
        max_stale=86400,
    )


@require_safe
def entertainment(request: HttpRequest):
    response = render(request, "web/pages/entertainment.html")
    return public_page_response(
        response,
        edge_max_age=300,
        max_stale=86400,
    )


@require_safe
def privacy(request: HttpRequest):
    response = render(request, "web/pages/privacy.html")
    return public_page_response(
        response,
        edge_max_age=300,
        max_stale=86400,
    )


@require_GET
def login(request: HttpRequest):
    response = render(request, "web/pages/login.html")
    return private_page_response(response)


@require_GET
def user(request: HttpRequest):
    response = render(request, "web/pages/user.html")
    return private_page_response(response)


# nginx will process this in prod
@require_GET
def favicon(request: HttpRequest):
    return HttpResponsePermanentRedirect(static("favicon.ico"))


@require_GET
def robots(request: HttpRequest):
    return HttpResponsePermanentRedirect(static("robots.txt"))


@require_GET
def llms(request: HttpRequest):
    return HttpResponsePermanentRedirect(static("llms.txt"))


# sync only
def page_not_found(request: HttpRequest, exception: Exception):
    user = getattr(request, "user", None)
    visitor = (
        user.get_username() if user is not None and user.is_authenticated else "visitor"
    )
    context = {"visitor": visitor}
    return private_page_response(
        TemplateResponse(request, "404.html", context=context, status=404)
    )


def server_error(request: HttpRequest):
    return private_page_response(render(request, "500.html", status=500))
