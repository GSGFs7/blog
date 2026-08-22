import asyncio

from ninja import Router

from api.markdown import Markdown
from api.schemas import MarkdownRenderRequest, MarkdownRenderResponse

router = Router()


@router.post("/render", response=MarkdownRenderResponse)
async def render_markdown_content(request, data: MarkdownRenderRequest):
    html = await asyncio.to_thread(Markdown().render, data.markdown)
    return {"html": html}
