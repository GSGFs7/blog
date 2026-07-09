import json
from pathlib import Path
from tempfile import TemporaryDirectory

from django.template import Context, Template
from django.test import SimpleTestCase, override_settings

from web.templatetags import vite


class ViteTemplateTagTests(SimpleTestCase):
    def tearDown(self):
        vite._load_manifest.cache_clear()
        super().tearDown()

    @override_settings(DEBUG=True)
    def test_vite_asset_uses_dev_server_in_debug(self):
        rendered = Template(
            "{% load vite %}{% vite_asset 'web/typescript/index.tsx' %}"
        ).render(Context())
        self.assertEqual(rendered, "http://localhost:5173/web/typescript/index.tsx")

    @override_settings(DEBUG=False, STATIC_URL="/static/")
    def test_vite_asset_uses_manifest_in_production(self):
        with TemporaryDirectory() as tmp_dir:
            manifest_dir = Path(tmp_dir) / "dist"
            manifest_dir.mkdir(parents=True)
            (manifest_dir / "manifest.json").write_text(
                json.dumps(
                    {"web/typescript/index.tsx": {"file": "assets/index-abc123.js"}}
                )
            )
            vite._load_manifest.cache_clear()

            with override_settings(STATIC_ROOT=tmp_dir):
                rendered = Template(
                    "{% load vite %}{% vite_asset 'web/typescript/index.tsx' %}"
                ).render(Context())

        self.assertEqual(rendered, "/static/dist/assets/index-abc123.js")

    @override_settings(DEBUG=False)
    def test_vite_asset_raises_when_manifest_is_missing(self):
        with TemporaryDirectory() as tmp_dir:
            vite._load_manifest.cache_clear()

            with override_settings(STATIC_ROOT=tmp_dir):
                with self.assertRaisesMessage(
                    RuntimeError, "Vite manifest not found. Run `pnpm run build` first."
                ):
                    Template(
                        "{% load vite %}{% vite_asset 'web/typescript/index.tsx' %}"
                    ).render(Context())
