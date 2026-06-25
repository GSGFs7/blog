def site_meta(request):
    """put site meta info here"""
    return {
        "SITE_TITLE": "GSGFs's blog",
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
    }
