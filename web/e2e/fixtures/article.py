import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import django
from asgiref.sync import async_to_sync
from django.test import RequestFactory, override_settings


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "blog.settings")
    django.setup()

    from api.markdown import Markdown
    from web.views.pages import blog_post_slug

    html, toc = Markdown().render_with_toc(
        "# Navigation fixture\n\n## Formula\n\n$$\nx^2 + y^2 = z^2\n$$\n\n"
        "```python\nprint('navigation')\n```\n"
    )
    post = SimpleNamespace(
        title="Navigation fixture",
        slug="e2e-navigation",
        content_html=html,
        toc=toc,
        layout="article",
        meta_description="Navigation stylesheet fixture",
        keywords="navigation",
        header_image=None,
        cover_image=None,
        published_at=None,
        content_update_at=None,
        category_id=None,
        tags=SimpleNamespace(all=lambda: []),
    )
    with (
        override_settings(
            DEBUG=True,
            APP_BUILD_ID=sys.argv[1],
            PAGE_NAVIGATION_MODE="native",
            VITE_DEV_SERVER_URL=sys.argv[2],
            SOLID_ISLANDS_SSR=False,
        ),
        patch("web.views.pages.aget_object_or_404", AsyncMock(return_value=post)),
    ):
        request = RequestFactory().get("/blog/e2e-navigation")
        response = async_to_sync(blog_post_slug)(request, post_slug=post.slug)
        response.render()
        sys.stdout.write(response.content.decode())


if __name__ == "__main__":
    main()
