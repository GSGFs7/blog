import json
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase, override_settings

from api.markdown.markdown_it import Markdown
from api.models import Gal, Post
from media_service.models import ImageResource


class TestMarkdownPostProcess(SimpleTestCase):
    def setUp(self):
        self.md = Markdown()

    def test_image_wrapping_and_centering(self):
        """Test that images are wrapped in a span with md-img-container class."""
        markdown_text = "![alt](test.png)"
        html = self.md.render(markdown_text)
        self.assertIn('<span class="md-img-container"', html)
        self.assertIn('<img src="test.png" alt="alt">', html)
        self.assertIn("</span>", html)

    def test_caption_priority_alt_only(self):
        """Test that data-caption uses alt when title is missing."""
        markdown_text = "![alt text](test.png)"
        html = self.md.render(markdown_text)
        self.assertIn('data-caption="alt text"', html)

    def test_caption_priority_title_wins(self):
        """Test that data-caption prioritizes title over alt."""
        markdown_text = '![alt text](test.png "title text")'
        html = self.md.render(markdown_text)
        self.assertIn('data-caption="title text"', html)
        self.assertIn('alt="alt text"', html)
        self.assertIn('title="title text"', html)

    def test_caption_escapes_special_characters_once(self):
        html = self.md.render('![alt &](test.png "title &")')

        self.assertIn('data-caption="title &amp;"', html)
        self.assertNotIn("&amp;amp;", html)

    def test_caption_only_title(self):
        """Test that data-caption works when only title is provided."""
        markdown_text = '![](test.png "only title")'
        html = self.md.render(markdown_text)
        self.assertIn('data-caption="only title"', html)

    def test_no_caption_if_both_missing(self):
        """Test that data-caption is empty if both alt and title are missing."""
        markdown_text = "![](test.png)"
        html = self.md.render(markdown_text)
        self.assertIn('data-caption=""', html)

    def test_multiple_images(self):
        """Test that multiple images in one document are all correctly processed."""
        markdown_text = "![img1](1.png)\n\n![img2](2.png)"
        html = self.md.render(markdown_text)
        self.assertEqual(html.count('class="md-img-container"'), 2)
        self.assertIn('data-caption="img1"', html)
        self.assertIn('data-caption="img2"', html)

    def test_image_inside_other_text(self):
        """
        Test that images inside paragraphs are correctly
        wrapped without breaking text.
        """
        markdown_text = "Text before ![alt](img.png) text after."
        html = self.md.render(markdown_text)
        self.assertIn('<p>Text before <span class="md-img-container"', html)
        self.assertIn("</span> text after.</p>", html)

    def test_pre_data_language(self):
        markdown_text = "```python\nprint('hello')\n```"
        html = self.md.render(markdown_text)
        self.assertIn('<pre data-language="python"', html)

    def test_pre_without_language_class(self):
        markdown_text = "```\nno language\n```"
        html = self.md.render(markdown_text)
        self.assertNotIn("data-language=", html)

    def test_pre_data_language_multiple_blocks(self):
        markdown_text = "```python\na = 1\n```\n\n```rust\nlet x = 1;\n```"
        html = self.md.render(markdown_text)
        self.assertIn('data-language="python"', html)
        self.assertIn('data-language="rust"', html)

    def test_pre_data_language_supports_nonword_language_names(self):
        html = self.md.render(
            "```c++\nint main() {}\n```\n\n"
            "```objective-c\n@interface App\n```\n\n"
            "```shell-session\n$ echo hello\n```\n\n"
            '<pre><code class="language-c++">raw</code></pre>'
        )

        self.assertEqual(html.count('data-language="c++"'), 2)
        self.assertIn('data-language="objective-c"', html)
        self.assertIn('data-language="shell-session"', html)

    def test_domain_injection(self):
        """Test that data-domain is injected only into the <span> tag."""
        markdown_text = "[google](https://google.com)"
        html = self.md.render(markdown_text)
        self.assertIn('<span data-domain="google.com">google</span>', html)
        self.assertNotIn('<a data-domain="google.com"', html)

    def test_domain_injection_uses_hostname_without_credentials_or_port(self):
        html = self.md.render("[private](https://user:password@example.com:8443/path)")

        self.assertIn('<span data-domain="example.com">private</span>', html)
        self.assertNotIn('data-domain="user:password@example.com:8443"', html)
        self.assertNotIn('data-domain="example.com:8443"', html)

    def test_domain_injection_supports_ipv6_and_idn(self):
        html = self.md.render(
            "[ipv6](https://[2001:db8::1]:8443/path) [idn](https://例子.测试/path)"
        )

        self.assertIn('<span data-domain="2001:db8::1">ipv6</span>', html)
        self.assertIn('<span data-domain="xn--fsqu00a.xn--0zwm56d">idn</span>', html)

    def test_domain_injection_ignores_non_http_and_invalid_urls(self):
        html = self.md.render(
            '<a href="mailto:test@example.com">mail</a> '
            '<a href="https://[invalid">invalid</a>'
        )

        self.assertNotIn("data-domain=", html)

    def test_domain_injection_is_idempotent(self):
        html = self.md.render(
            '<a href="https://example.com">'
            '<span data-domain="example.com">existing</span></a>'
        )

        self.assertEqual(html.count("data-domain="), 1)

    def test_sanitizes_dangerous_html(self):
        markdown_text = """
<span class="heimu" onclick="alert(1)">secret</span>
<script>alert(1)</script>
<a href="javascript:alert(1)">bad</a>
<img src="x" onerror="alert(1)">
"""
        html = self.md.render(markdown_text)

        self.assertIn('<span class="heimu">secret</span>', html)
        self.assertIn('<a rel="noopener noreferrer">bad</a>', html)
        self.assertNotIn("alert(1)", html)
        self.assertNotIn("javascript:", html)
        self.assertNotIn("onclick", html)
        self.assertNotIn("onerror", html)
        self.assertNotIn("<script", html)

    def test_sanitizer_rejects_active_svg_and_non_image_data_urls(self):
        html = self.md.render(
            '<svg onload="alert(1)"><circle></circle></svg>'
            "<math><mrow><mi>x</mi></mrow></math>"
            '<img src="safe.png" '
            'style="background-image:url(data:text/html,boom);width:1px">'
        )

        self.assertIn("<svg></svg>", html)
        self.assertNotIn("<circle", html)
        self.assertNotIn("onload", html)
        self.assertNotIn("alert(1)", html)
        self.assertIn("<math><mrow><mi>x</mi></mrow></math>", html)
        self.assertIn('<img src="safe.png">', html)
        self.assertNotIn("data:text/html", html)
        self.assertNotIn("style=", html)

    def test_sanitizer_handles_malformed_html(self):
        html = self.md.render(
            '<script><p>hidden</p></script><div><span onclick="alert(1)">safe'
        )

        self.assertEqual(html, "<div><span>safe\n</span></div>")

    def test_task_list_survives_sanitizer(self):
        html = self.md.render("- [x] done\n- [ ] todo")

        self.assertIn('class="contains-task-list"', html)
        self.assertIn('class="task-list-item"', html)
        self.assertIn('class="task-list-item-checkbox"', html)
        self.assertIn('type="checkbox"', html)
        self.assertIn('disabled=""', html)
        self.assertIn('checked=""', html)

    def test_footnotes_survive_sanitizer(self):
        html = self.md.render("hello[^1]\n\n[^1]: note")

        self.assertIn('<section class="footnotes">', html)
        self.assertIn('class="footnote-ref"', html)
        self.assertIn('id="fnref1"', html)
        self.assertIn('href="#fn1"', html)
        self.assertIn('class="footnote-backref"', html)

    def test_math_survives_sanitizer(self):
        html = self.md.render("$$\nE = mc^2\n$$")

        self.assertIn('class="math-block"', html)
        self.assertIn('class="katex"', html)
        self.assertIn('xmlns="http://www.w3.org/1998/Math/MathML"', html)
        self.assertIn('encoding="application/x-tex"', html)
        self.assertIn('style="height:', html)

    def test_python_wasm_directive_mounts_repl_island(self):
        html = self.md.render('<div class="directive python-wasm"></div>')

        self.assertIn('data-solid-island="PythonREPL"', html)

    def test_directives_only_forward_allowed_component_props(self):
        html = self.md.render(
            '<div class="directive counter" initial="1024" onclick="alert(1)"></div>'
            '<div class="directive chart" formula="x^2" x-min="-1" '
            'y-max="2" ignored="value"></div>'
        )

        self.assertIn(
            'data-solid-island="Counter" '
            'data-props="{&quot;initial&quot;:&quot;1024&quot;}"',
            html,
        )
        self.assertIn(
            'data-solid-island="Chart" '
            'data-props="{&quot;formula&quot;:&quot;x^2&quot;,'
            '&quot;x-min&quot;:&quot;-1&quot;,&quot;y-max&quot;:&quot;2&quot;}"',
            html,
        )
        self.assertNotIn("onclick", html)
        self.assertNotIn("ignored", html)

    def test_terminal_directive_is_rendered(self):
        markdown_text = """
:::terminal{title="数据库迁移" shell="bash" prompt="$"}
```command
uv run manage.py migrate
```

```output
No migrations to apply.
```

```error
warning
```
:::
"""
        html = self.md.render(markdown_text)

        self.assertIn('class="terminal"', html)
        self.assertIn('data-shell="bash"', html)
        self.assertIn('role="group"', html)
        self.assertIn('aria-label="数据库迁移"', html)
        self.assertIn('style="--terminal-prompt:&quot;$ &quot;"', html)
        self.assertIn('class="terminal-title"', html)
        self.assertIn('data-language="command"', html)
        self.assertIn('data-language="output"', html)
        self.assertIn('data-language="error"', html)
        self.assertNotIn('class="directive terminal"', html)
        self.assertNotIn("data-solid-island", html)

    def test_terminal_invalid_metadata_uses_defaults(self):
        markdown_text = """
:::terminal{shell="invalid shell" prompt="x; color: red"}
```command
echo hello
```
:::
"""
        html = self.md.render(markdown_text)

        self.assertIn('data-shell="bash"', html)
        self.assertIn('style="--terminal-prompt:&quot;$ &quot;"', html)
        self.assertNotIn("color: red", html)

    def test_terminal_shell_commands_are_highlighted(self):
        markdown_text = """
:::terminal{title="Base64" shell="zsh" prompt="❯"}
```zsh
echo "hello" | base64
```

```output
aGVsbG8K
```
:::
"""
        html = self.md.render(markdown_text)

        self.assertIn('data-shell="zsh"', html)
        self.assertIn('style="--terminal-prompt:&quot;❯ &quot;"', html)
        self.assertIn('data-language="zsh"', html)
        self.assertRegex(
            html,
            r'class="[^"]*syntect-function[^"]*">echo</span>',
        )
        self.assertRegex(
            html,
            r'class="[^"]*syntect-function[^"]*">base64</span>',
        )

    def test_non_terminal_div_style_is_removed(self):
        html = self.md.render('<div style="width: 100%">content</div>')

        self.assertIn("<div>content</div>", html)
        self.assertNotIn("style=", html)


@override_settings(MEDIA_URL="/media/")
class TestMarkdownImageOptimization(TestCase):
    checksum = "d45c3754209b10b7c7ecab223d712ddbc21dde4e58cd819f05381c92d3327aa3"

    def create_image_resource(self, checksum: str | None = None) -> ImageResource:
        checksum = checksum or self.checksum
        return ImageResource.objects.create(
            checksum=checksum,
            file=f"images/raw/{checksum[:2]}/{checksum[2:4]}/{checksum}.jpg",
            avif_file=f"images/avif/{checksum[:2]}/{checksum[2:4]}/{checksum}.avif",
            webp_file=f"images/webp/{checksum[:2]}/{checksum[2:4]}/{checksum}.webp",
            width=916,
            height=916,
            size=1,
            mime_type="image/jpeg",
            placeholder="data:image/webp;base64,test+value",
        )

    def test_image_resource_is_rendered_as_wrapped_picture(self):
        resource = self.create_image_resource()

        with self.assertNumQueries(1):
            html = Markdown().render(f"![caption]({resource.checksum})")

        self.assertIn('<span class="md-img-container" data-caption="caption">', html)
        self.assertIn("<picture>", html)
        self.assertIn('type="image/avif"', html)
        self.assertIn('type="image/webp"', html)
        self.assertIn(f'src="{resource.file.url}"', html)
        self.assertIn('class="image-placeholder"', html)
        self.assertIn("background-image:url(data:image/webp;base64,test+value)", html)
        self.assertIn("background-size:cover", html)
        self.assertNotIn("</picture?", html)
        self.assertNotIn("\\+", html)

    def test_current_storage_url_is_optimized(self):
        resource = self.create_image_resource()

        with self.assertNumQueries(1):
            html = Markdown().render(f"![caption]({resource.file.url})")

        self.assertIn("<picture>", html)
        self.assertIn(f'src="{resource.file.url}"', html)

    @override_settings(MEDIA_URL="https://cdn.example/media/")
    def test_remote_storage_url_is_optimized(self):
        resource = self.create_image_resource()

        with self.assertNumQueries(1):
            html = Markdown().render(f"![caption]({resource.file.url})")

        self.assertIn("<picture>", html)
        self.assertIn(f'src="{resource.file.url}"', html)

    def test_external_checksum_url_is_not_optimized(self):
        resource = self.create_image_resource()
        source = f"https://example.com/images/{resource.checksum}.jpg"

        with self.assertNumQueries(1):
            html = Markdown().render(f"![caption]({source})")

        self.assertNotIn("<picture>", html)
        self.assertIn(f'src="{source}"', html)
        self.assertNotIn(resource.file.url, html)

    @override_settings(
        IMAGE_PICTURE_URL_PREFIXES={
            "https://uploads.example/media/": {
                "avif": "https://uploads.example/avif/",
                "webp": "https://uploads.example/webp/",
            }
        }
    )
    def test_configured_picture_source_prefix_is_optimized(self):
        resource = self.create_image_resource()
        source = f"https://uploads.example/media/{resource.checksum}.jpg"

        with self.assertNumQueries(1):
            html = Markdown().render(f"![caption]({source})")

        self.assertIn("<picture>", html)
        self.assertIn(f'src="{resource.file.url}"', html)

    def test_unknown_checksum_is_not_optimized(self):
        checksum = "a" * 64

        with self.assertNumQueries(1):
            html = Markdown().render(f"![caption]({checksum})")

        self.assertNotIn("<picture>", html)
        self.assertIn(f'src="{checksum}"', html)

    def test_images_without_checksums_do_not_query_the_database(self):
        with self.assertNumQueries(0):
            html = Markdown().render("![caption](https://example.com/image.jpg)")

        self.assertNotIn("<picture>", html)

    def test_multiple_images_use_one_bulk_query(self):
        first = self.create_image_resource()
        second = self.create_image_resource("e" * 64)

        with self.assertNumQueries(1):
            html = Markdown().render(
                f"![first]({first.checksum})\n\n![second]({second.checksum})"
            )

        self.assertEqual(html.count("<picture>"), 2)

    def test_missing_derived_formats_are_omitted(self):
        resource = self.create_image_resource()
        resource.avif_file = None
        resource.webp_file = None
        resource.placeholder = ""
        resource.save(update_fields=["avif_file", "webp_file", "placeholder"])

        with self.assertNumQueries(1):
            html = Markdown().render(f"![caption]({resource.checksum})")

        self.assertIn("<picture>", html)
        self.assertNotIn("<source", html)
        self.assertNotIn("image-placeholder", html)

    def test_resolver_does_not_access_responsive_variants(self):
        resource = self.create_image_resource()

        with self.assertNumQueries(1):
            html = Markdown().render(f"![caption]({resource.checksum})")

        self.assertIn("<picture>", html)


class TestMarkdownProductionEntrypoints(TestCase):
    def test_preview_api_uses_native_suffix(self):
        response = self.client.post(
            "/api/markdown/render",
            data=json.dumps(
                {"markdown": "[link](https://example.com) <script>alert(1)</script>"}
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        html = response.json()["html"]
        self.assertIn('data-domain="example.com"', html)
        self.assertNotIn("alert(1)", html)

    @patch("api.routers.markdown.logger.exception")
    @patch(
        "api.routers.markdown.Markdown.render",
        side_effect=RuntimeError("internal render details"),
    )
    def test_preview_api_returns_service_unavailable_on_render_failure(
        self, _render, log_exception
    ):
        response = self.client.post(
            "/api/markdown/render",
            data=json.dumps({"markdown": "# preview"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json(),
            {"message": "Markdown rendering temporarily unavailable"},
        )
        self.assertNotContains(response, "internal render details", status_code=503)
        log_exception.assert_called_once_with("Markdown preview rendering failed")

    def test_post_save_uses_native_suffix_and_toc(self):
        post = Post.objects.create(
            title="Native markdown signal",
            slug="native-markdown-signal",
            content="# Heading\n\n[link](https://example.com)",
        )

        post.refresh_from_db()
        self.assertIn('data-domain="example.com"', post.content_html)
        self.assertEqual(
            post.toc,
            [{"level": 1, "slug": "heading", "text": "Heading"}],
        )

    @patch("api.vndb.query_vn", return_value={"results": []})
    def test_gal_save_uses_native_suffix(self, _query_vn):
        gal = Gal.objects.create(
            vndb_id="v999999",
            review="[link](https://example.com)<script>alert(1)</script>",
        )

        gal.refresh_from_db()
        self.assertIn('data-domain="example.com"', gal.review_html)
        self.assertNotIn("alert(1)", gal.review_html)
