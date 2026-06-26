from tempfile import TemporaryDirectory

from django.test import SimpleTestCase, override_settings

from api.widgets import MarkdownEditorWidget
from web.templatetags import vite


class MarkdownEditorWidgetTests(SimpleTestCase):
    def tearDown(self):
        vite._load_manifest.cache_clear()
        super().tearDown()

    @override_settings(DEBUG=False)
    def test_widget_init_does_not_require_vite_manifest(self):
        with TemporaryDirectory() as tmp_dir:
            with override_settings(STATIC_ROOT=tmp_dir):
                widget = MarkdownEditorWidget()

        self.assertEqual(widget.attrs["data-editor-target"], "content")
