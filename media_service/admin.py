from io import BytesIO

from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from media_service.constants import IMAGE_ALLOWED_FORMAT
from media_service.models import Image
from media_service.tasks import process_image


# Register your models here.
class ImageAdminForm(forms.ModelForm):
    file = forms.ImageField(required=True, label="image")

    class Meta:
        model = Image
        fields = ["original_name", "alt_text", "description"]
        help_texts = {
            "checksum": "blake3 算法得到的哈希值",
        }

    def __init__(self, *args, **kwargs):
        # set the admin user as uploader
        self.uploader = kwargs.pop("uploader", None)
        super().__init__(*args, **kwargs)

        if self.instance.pk is None:
            self.fields["file"] = forms.ImageField(required=True, label="image")
        else:
            if "file" in self.fields:
                del self.fields["file"]

    def clean_file(self):
        file = self.cleaned_data.get("file")
        if not file:
            return file

        if file.content_type not in IMAGE_ALLOWED_FORMAT:
            raise ValidationError(
                f"Not allowed format: {file.content_type}. "
                f"Allowed format: {', '.join(IMAGE_ALLOWED_FORMAT)}"
            )
        return file

    def save(self, commit=True):
        # Call super().save(commit=False) to ensure self.save_m2m
        # is initialized by Django
        instance = super().save(commit=False)
        file = self.cleaned_data.get("file")

        if file:
            file.seek(0)
            content = BytesIO(file.read())
            img, *_ = Image.create_from_file(
                content,
                file.name,
                uploader=self.uploader,
            )

            img.original_name = self.cleaned_data.get("original_name") or file.name
            img.alt_text = self.cleaned_data.get("alt_text", "")
            img.description = self.cleaned_data.get("description", "")

            if commit:
                img.save()

            return img

        if commit:
            instance.save()
            # self.save_m2m()

        return instance


class ImageAdmin(admin.ModelAdmin):
    form = ImageAdminForm
    actions = ["trigger_image_processing"]
    readonly_fields = [
        "preview_large",
        "copyable_url",
        "uploader_display",
        "resource_info",
        "mime_type",
        "size",
        "size_formatted",
        "width",
        "height",
        "checksum",
        "created_at",
        "updated_at",
        "id",
        "width_px",
        "height_px",
    ]

    def get_fieldsets(self, request, obj=None):
        if obj is None:
            # new
            return [
                (
                    None,
                    {
                        "fields": [
                            "file",
                            "preview_large",
                            "original_name",
                            "alt_text",
                            "description",
                        ]
                    },
                ),
                (
                    "upload info",
                    {"fields": ["uploader_display", "created_at", "updated_at"]},
                ),
            ]
        else:
            # edit
            return [
                (
                    None,
                    {
                        "fields": [
                            "id",
                            "preview_large",
                            "original_name",
                            "alt_text",
                            "description",
                        ]
                    },
                ),
                (
                    "resource info",
                    {
                        "fields": [
                            "resource_info",
                            "copyable_url",
                            "mime_type",
                            "size_formatted",
                            "width_px",
                            "height_px",
                            "checksum",
                        ],
                    },
                ),
                (
                    "upload info",
                    {"fields": ["uploader_display", "created_at", "updated_at"]},
                ),
            ]

    list_display = [
        "original_name",
        "preview_icon",
        "mime_type",
        "size_formatted",
        "created_at",
    ]
    list_filter = ["created_at"]
    search_fields = ["original_name", "alt_text", "description"]
    date_hierarchy = "created_at"

    def get_form(self, request, obj=None, change=False, **kwargs):
        form_class = super().get_form(request, obj, change, **kwargs)

        class RequestBoundImageAdminForm(form_class):
            def __init__(self, *args, **inner_kwargs):
                # put the admin into the form args
                inner_kwargs["uploader"] = request.user
                super().__init__(*args, **inner_kwargs)

        return RequestBoundImageAdminForm

    def save_model(self, request, obj, form, change):
        if getattr(obj, "uploader", None) is None:
            # if admin miss, set it again
            obj.uploader = request.user
        super().save_model(request, obj, form, change)

    @admin.action(description="Trigger image processing")
    def trigger_image_processing(self, request, queryset):
        resource_ids = {
            image.resource_id for image in queryset if image.resource_id is not None
        }

        for resource_id in resource_ids:
            process_image.delay(resource_id, force=True)

        self.message_user(
            request, f"Triggered image processing for {len(resource_ids)} resources."
        )

    @admin.display(description="size")
    def size_formatted(self, obj: Image):
        size = obj.resource.size
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} KiB"
        else:
            return f"{size / (1024 * 1024):.1f} MiB"

    @admin.display(description="thumbnail")
    def preview_icon(self, obj: Image):
        if obj.resource and obj.resource.file:
            return mark_safe(
                f'<img src="{
                    obj.resource.thumbnail.url
                    if obj.resource.thumbnail
                    else obj.resource.file.url
                }"'
                f' height="100px"'
                f' style="width: auto; max-width: 100%; object-fit: contain;"'
                f"/>"
            )
        return "no img"

    @admin.display(description="image preview")
    def preview_large(self, obj: Image):
        if obj.resource and obj.resource.file:
            return mark_safe(
                f'<img src="{
                    obj.resource.thumbnail.url
                    if obj.resource.thumbnail
                    else obj.resource.file.url
                }"'
                f' style="max-width: 300px; max-height: 300px;"'
                f"/>"
            )
        return "no img"

    @admin.display(description="resource info")
    def resource_info(self, obj: Image):
        if obj.resource:
            return f"ID: {obj.resource.id}"
        return "no resource"

    @admin.display(description="image url")
    def copyable_url(self, obj: Image):
        if not obj.pk or not obj.resource or not obj.resource.file:
            return "-"
        return format_html(
            '<div class="copy-image-url-widget">'
            "<code>{}</code> "
            '<button type="button" class="button" data-copy-image-url="{}" '
            'onclick="navigator.clipboard.writeText(this.dataset.copyImageUrl)"'
            ">"
            "Copy URL"
            "</button>"
            "</div>",
            obj.url,
            obj.url,
        )

    @admin.display(description="uploader")
    def uploader_display(self, obj: Image):
        if not obj.pk or obj.uploader is None:
            return "-"
        return str(obj.uploader)

    @admin.display(description="MIME type")
    def mime_type(self, obj: Image):
        return obj.resource.mime_type if obj.resource else "-"

    @admin.display(description="width")
    def width(self, obj: Image):
        return obj.resource.width if obj.resource else "-"

    @admin.display(description="height")
    def height(self, obj: Image):
        return obj.resource.height if obj.resource else "-"

    @admin.display(description="checksum")
    def checksum(self, obj: Image):
        return obj.resource.checksum if obj.resource else "-"

    @admin.display(description="size")
    def size(self, obj: Image):
        return obj.resource.size if obj.resource else 0

    @admin.display(description="width")
    def width_px(self, obj: Image):
        return f"{obj.resource.width} px"

    @admin.display(description="height")
    def height_px(self, obj: Image):
        return f"{obj.resource.width} px"


admin.site.register(Image, ImageAdmin)
