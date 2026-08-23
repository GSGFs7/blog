import asyncio
import logging

from ninja import Router
from ninja.errors import HttpError

from api.markdown import Markdown
from api.schemas import MarkdownRenderRequest, MarkdownRenderResponse

logger = logging.getLogger(__name__)

router = Router()


@router.post("/render", response=MarkdownRenderResponse)
async def render_markdown_content(request, data: MarkdownRenderRequest):
    try:
        html = await asyncio.to_thread(Markdown().render, data.markdown)
    except Exception as exc:
        logger.exception("Markdown preview rendering failed")
        raise HttpError(503, "Markdown rendering temporarily unavailable") from exc
    return {"html": html}
