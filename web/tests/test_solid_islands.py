from django.template import Context, Template
from django.test import TestCase

# use vite build frontend under ssr mode first
# otherwise, this will raise a error


class SolidIslandsTestCase(TestCase):
    def test_solid_island_tag(self):
        template = Template("{% load solid_islands %}{% solid_island 'Counter' %}")
        rendered = template.render(Context({}))

        self.assertIn('data-solid-island="Counter"', rendered)
        self.assertIn("data-solid-ssr", rendered)
        self.assertIn("props", rendered)
