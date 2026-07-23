from unittest.mock import patch

from django.template import Context, Template
from django.test import SimpleTestCase, override_settings


class SolidIslandsTestCase(SimpleTestCase):
    manifest = {
        "islands": {
            "Counter": {
                "props": {"initial": 0, "label": "default"},
                "html": "<div><span>Count: 0</span></div>",
            }
        }
    }

    @override_settings(SOLID_ISLANDS_SSR=False)
    def test_client_rendered_wrapper_does_not_load_manifest(self):
        template = Template(
            "{% load solid_islands %}{% solid_island 'Counter' initial=3 %}"
        )
        rendered = template.render(Context({}))

        self.assertIn('data-solid-island="Counter"', rendered)
        self.assertNotIn("data-solid-ssr", rendered)
        self.assertIn("&quot;initial&quot;:3", rendered)
        self.assertNotIn("Count: 0", rendered)

    @override_settings(SOLID_ISLANDS_SSR=True)
    @patch("web.templatetags.solid_islands._load_manifest")
    def test_server_rendered_wrapper_uses_manifest(self, load_manifest):
        load_manifest.return_value = self.manifest
        template = Template("{% load solid_islands %}{% solid_island 'Counter' %}")
        rendered = template.render(Context({}))

        load_manifest.assert_called_once()
        self.assertIn('data-solid-island="Counter"', rendered)
        self.assertIn("data-solid-ssr", rendered)
        self.assertIn("&quot;initial&quot;:0", rendered)
        self.assertIn("&quot;label&quot;:&quot;default&quot;", rendered)
        self.assertIn("<span>Count: 0</span>", rendered)

    @override_settings(SOLID_ISLANDS_SSR=True)
    @patch("web.templatetags.solid_islands._load_manifest")
    def test_template_props_override_manifest_defaults(self, load_manifest):
        load_manifest.return_value = self.manifest
        template = Template(
            "{% load solid_islands %}"
            "{% solid_island 'Counter' initial=1024 label=label %}"
        )
        rendered = template.render(Context({"label": "custom"}))

        self.assertIn("&quot;initial&quot;:1024", rendered)
        self.assertIn("&quot;label&quot;:&quot;custom&quot;", rendered)

    @override_settings(SOLID_ISLANDS_SSR=True)
    @patch("web.templatetags.solid_islands._load_manifest")
    def test_props_are_escaped_inside_the_data_attribute(self, load_manifest):
        load_manifest.return_value = self.manifest
        template = Template(
            "{% load solid_islands %}{% solid_island 'Counter' label=label %}"
        )
        rendered = template.render(Context({"label": '"><script>alert(1)</script>'}))

        self.assertNotIn("<script>alert(1)</script>", rendered)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", rendered)
