from typing import Any

import orjson
from django.http import HttpRequest
from ninja import NinjaAPI
from ninja.errors import HttpError
from ninja.parser import Parser
from ninja.renderers import BaseRenderer
from ninja.responses import NinjaJSONEncoder
from ninja.types import DictStrAny

from accounts.decorators import otp_staff_required

from .routers.anime import router as anime_router
from .routers.auth import router as auth_router
from .routers.category import router as categories_router
from .routers.comment import router as comment_router
from .routers.gal import router as gal_router
from .routers.health import router as health_router
from .routers.image import router as image_router
from .routers.mail import router as mail_router
from .routers.markdown import router as markdown_router
from .routers.page import router as page_router
from .routers.post import router as posts_router
from .routers.root import router as root_router


# useless, 1.00x faster in real world
class UltraSpeedJSONParser(Parser):
    def parse_body(self, request: HttpRequest) -> DictStrAny:
        return orjson.loads(request.body)


# useless, 1.03x faster in real world
class UltraSpeedJSONRender(BaseRenderer):
    media_type = "application/json"
    encoder = NinjaJSONEncoder()

    def render(
        self,
        request: HttpRequest,
        data: Any,
        *,
        response_status: int,
    ) -> Any:
        return orjson.dumps(data, default=self.encoder.default)


api = NinjaAPI(
    title="GSGFs blog API",
    description="GSGFs blog backend API",
    version="1.0.0",
    urls_namespace="api",
    parser=UltraSpeedJSONParser(),
    renderer=UltraSpeedJSONRender(),
    docs_decorator=otp_staff_required,
)


# Handler the error be raised
@api.exception_handler(HttpError)
def http_error_handler(request, exc: HttpError):
    return api.create_response(request, {"message": str(exc)}, status=exc.status_code)


# convert to openapi 3.0, PyCharm not support 3.1 yet
# original_get_schema = api.get_openapi_schema
# api.get_openapi_schema = convert_openapi(original_get_schema)  # wrap


api.add_router("/anime", anime_router)
api.add_router("/auth", auth_router)
api.add_router("/category", categories_router)
api.add_router("/comment", comment_router)
api.add_router("/gal", gal_router)
# api.add_router("/guest", guest_router)
api.add_router("/health", health_router)
api.add_router("/image", image_router)
api.add_router("/mail", mail_router)
api.add_router("/markdown", markdown_router)
api.add_router("/page", page_router)
api.add_router("/post", posts_router)
api.add_router("/", root_router)
