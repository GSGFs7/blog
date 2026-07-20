import shutil
import tempfile

from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.core.files.base import ContentFile
from django.template import Context, Template
from django.test import TestCase, override_settings

from media_service.models import Image, ImageResource, ImageVariant
from media_service.templatetags.media_tags import render_image, to_thumbnail


class MediaTagsTestCase(TestCase):
    def setUp(self):
        # Setup temporary media root to avoid polluting actual media directory
        self.media_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media_root, ignore_errors=True)
        self.override = override_settings(
            MEDIA_ROOT=self.media_root, SECURE_SSL_REDIRECT=False
        )
        self.override.enable()
        self.addCleanup(self.override.disable)

        self.user = User.objects.create_user(username="testuser")
        self.resource = ImageResource.objects.create(
            checksum="a" * 64,
            width=100,
            height=100,
            size=1000,
            mime_type="image/jpeg",
            file=ContentFile(b"fake image content", name="test.jpg"),
            placeholder="data:image/webp;base64,cGxhY2Vob2xkZXI=",
        )
        content_type = ContentType.objects.get_for_model(self.user)
        self.image = Image.objects.create(
            resource=self.resource,
            original_name="test.jpg",
            uploader_type=content_type,
            uploader_id=self.user.id,
            alt_text="Test Alt Text",
        )

    def test_render_image_none(self):
        self.assertEqual(render_image(None), "")
        self.assertEqual(render_image(""), "")

    def test_render_image_url_string(self):
        url = "/media/test.jpg"
        result = render_image(url, alt="Alt", class_name="cls")
        self.assertIn(f'src="{url}"', result)
        self.assertIn('alt="Alt"', result)
        self.assertIn('class="cls"', result)
        self.assertIn('loading="lazy"', result)

    def test_render_image_rejects_unknown_kwargs(self):
        with self.assertRaisesRegex(TypeError, "unknown"):
            render_image("/media/test.jpg", unknown="value")

    def test_render_image_escapes_style_and_data_attribute_values(self):
        template = Template(
            "{% load media_tags %}"
            "{% render_image image style=style data_testid=testid %}"
        )
        result = template.render(
            Context(
                {
                    "image": "/media/test.jpg",
                    "style": 'object-fit: cover;" onerror="alert(1)',
                    "testid": 'hero" onload="alert(1)',
                }
            )
        )

        self.assertIn('style="object-fit: cover;&quot; onerror=&quot;alert(1)"', result)
        self.assertIn('data-testid="hero&quot; onload=&quot;alert(1)"', result)
        self.assertNotIn(' onerror="alert(1)"', result)
        self.assertNotIn(' onload="alert(1)"', result)

    @override_settings(
        IMAGE_PICTURE_URL_PREFIXES={
            "https://uploads.example.test/raw/": {
                "avif": "https://uploads.example.test/avif/",
                "webp": "https://uploads.example.test/webp/",
            }
        }
    )
    def test_render_image_url_string_with_known_variants(self):
        url = "https://uploads.example.test/raw/a1/b2/image.jpeg"

        result = render_image(
            url,
            alt="Alt",
            class_name="picture",
            img_class="image",
            sizes="50vw",
            fetch_priority="high",
            style="object-fit: cover;",
            data_testid="hero",
        )

        self.assertIn('<picture class="picture">', result)
        self.assertIn(
            'srcset="https://uploads.example.test/avif/a1/b2/image.avif"', result
        )
        self.assertIn(
            'srcset="https://uploads.example.test/webp/a1/b2/image.webp"', result
        )
        self.assertIn(f'src="{url}"', result)
        self.assertIn('class="image"', result)
        self.assertIn('sizes="50vw"', result)
        self.assertIn('fetchpriority="high"', result)
        self.assertIn('style="object-fit: cover;"', result)
        self.assertIn('data-testid="hero"', result)

    def test_render_image_resource(self):
        result = render_image(self.resource, class_name="picture-cls")
        self.assertIn("<picture", result)
        self.assertIn('class="picture-cls"', result)
        self.assertIn(f'src="{self.resource.file.url}"', result)
        self.assertIn(
            "background-image: url(data:image/webp;base64,cGxhY2Vob2xkZXI=)",
            result,
        )

    def test_render_image_obj(self):
        result = render_image(self.image)
        self.assertIn("<picture", result)
        self.assertIn(f'alt="{self.image.alt_text}"', result)
        self.assertIn(f'src="{self.image.resource.file.url}"', result)

    def test_render_image_checksum_string(self):
        result = render_image(self.resource.checksum)
        self.assertIn("<picture", result)
        self.assertIn(f'src="{self.resource.file.url}"', result)

    def test_render_image_with_variants(self):
        self.resource.avif_file = ContentFile(b"avif content", name="test.avif")
        self.resource.webp_file = ContentFile(b"webp content", name="test.webp")
        self.resource.save()

        result = render_image(self.resource)
        self.assertIn('type="image/avif"', result)
        self.assertIn('type="image/webp"', result)
        self.assertIn(f'srcset="{self.resource.avif_url}"', result)
        self.assertIn(f'srcset="{self.resource.webp_url}"', result)

    def test_render_image_with_responsive_variants(self):
        avif_320 = ImageVariant.objects.create(
            resource=self.resource,
            file=ContentFile(b"avif 320", name="test-320.avif"),
            format=ImageVariant.Format.AVIF,
            width=320,
            height=180,
            size=8,
        )
        avif_640 = ImageVariant.objects.create(
            resource=self.resource,
            file=ContentFile(b"avif 640", name="test-640.avif"),
            format=ImageVariant.Format.AVIF,
            width=640,
            height=360,
            size=8,
        )
        webp_320 = ImageVariant.objects.create(
            resource=self.resource,
            file=ContentFile(b"webp 320", name="test-320.webp"),
            format=ImageVariant.Format.WEBP,
            width=320,
            height=180,
            size=8,
        )

        sizes = "(max-width: 768px) 100vw, 768px"
        result = render_image(self.resource, sizes=sizes)

        self.assertIn(
            f'srcset="{avif_320.file.url} 320w, {avif_640.file.url} 640w"',
            result,
        )
        self.assertIn(f'srcset="{webp_320.file.url} 320w"', result)
        self.assertEqual(result.count(f'sizes="{sizes}"'), 3)

    def test_to_thumbnail_none(self):
        self.assertEqual(to_thumbnail(None), "")
        self.assertEqual(to_thumbnail(""), "")

    def test_to_thumbnail_url_string(self):
        url = "/media/test.jpg"
        self.assertEqual(to_thumbnail(url), url)

    def test_to_thumbnail_resource(self):
        # No thumbnail yet, should return file url
        self.assertEqual(to_thumbnail(self.resource), self.resource.file.url)

        self.resource.thumbnail = ContentFile(b"thumb content", name="test_thumb.jpg")
        self.resource.save()
        self.assertEqual(to_thumbnail(self.resource), self.resource.thumbnail.url)

    def test_to_thumbnail_image_obj(self):
        self.assertEqual(to_thumbnail(self.image), self.image.resource.file.url)

        self.resource.thumbnail = ContentFile(b"thumb content", name="test_thumb.jpg")
        self.resource.save()
        self.assertEqual(to_thumbnail(self.image), self.image.resource.thumbnail.url)

    def test_to_thumbnail_checksum_string(self):
        self.assertEqual(to_thumbnail(self.resource.checksum), self.resource.file.url)

    def test_template_integration(self):
        template = Template(
            '{% load media_tags %}{% render_image res alt="Alt" '
            "data_blog_header_image=True %}"
        )
        context = Context({"res": self.resource})
        rendered = template.render(context)
        self.assertIn("<picture", rendered)
        self.assertIn('src="', rendered)
        self.assertIn("data-blog-header-image", rendered)
