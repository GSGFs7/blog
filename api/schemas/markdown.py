from ninja import Schema


class MarkdownRenderRequest(Schema):
    markdown: str


class MarkdownRenderResponse(Schema):
    html: str
