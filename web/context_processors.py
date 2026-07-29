from django.conf import settings


def site_meta(request):
    """put site meta info here"""
    return {
        "SITE_TITLE": "GSGFs's blog",
        "SITE_DESCRIPTION": (
            "GSGFs's personal blog — writing about programming, technology, and life."
        ),
        "SITE_AUTHOR": "GSGFs",
        "SITE_NAV_ITEM": [
            {
                "label": "Home",
                "href": "/",
            },
            {
                "label": "Blog",
                "href": "/blog",
            },
            {
                "label": "Entertainment",
                "href": "/entertainment",
            },
            {
                "label": "About",
                "href": "/about",
            },
        ],
        # without tailing '/'
        "SITE_CANONICAL": "https://gsgfs.moe",
        "APP_BUILD_ID": settings.APP_BUILD_ID,
        "APP_NAVIGATION_VERSION": "1",
        # CF's JSD
        "CLOUDFLARE_JSD_ENABLED": settings.CLOUDFLARE_JSD_ENABLED,
    }
