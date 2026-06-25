from django import forms
from django.templatetags.static import static

from web.templatetags.vite import vite_asset


class MarkdownEditorWidget(forms.Textarea):
    """This widget just mark the textarea element which solid will replace"""

    def __init__(self):
        super().__init__()
        self.attrs = {
            "class": "solid-markdown-editor vLargeTextField",
            "data-editor-target": "content",
            "data-katex-css-url": static("katex/katex.min.css"),
            "data-markdown-css-url": vite_asset("web/typescript/styles/markdown.css"),
            "cols": "40",
            "rows": "10",
        }
