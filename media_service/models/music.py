import os

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

from .base import BaseModel


def music_upload_path(instance: "MusicResource", filename: str) -> str:
    ext = os.path.splitext(filename)[-1].lower()
    return (
        f"musics/"
        f"{instance.checksum[:2]}/"
        f"{instance.checksum[2:4]}/"
        f"{instance.checksum}{ext}"
    )


# TODO: GC
class MusicResource(BaseModel):
    checksum = models.CharField(max_length=64, unique=True)

    file = models.FileField(upload_to=music_upload_path)

    size = models.PositiveIntegerField()
    mime_type = models.CharField(max_length=80)
    duration = models.PositiveIntegerField(null=True, blank=True)
    bitrate = models.PositiveIntegerField(null=True, blank=True)
    sample_rate = models.PositiveIntegerField(null=True, blank=True)
    channels = models.PositiveIntegerField(null=True, blank=True)
    codec = models.CharField(max_length=80, blank=True)


class Music(BaseModel):
    resource = models.ForeignKey(
        MusicResource, on_delete=models.CASCADE, related_name="references"
    )
    original_name = models.CharField(max_length=255, blank=True)

    # metadata
    title = models.CharField(max_length=255, blank=True)
    artist = models.CharField(max_length=255, blank=True)
    album = models.CharField(max_length=255, blank=True)
    album_artist = models.CharField(max_length=255, blank=True)
    track_number = models.PositiveSmallIntegerField(null=True, blank=True)
    disc_number = models.PositiveSmallIntegerField(null=True, blank=True)
    release_data = models.CharField(max_length=40, blank=True)
    genre = models.CharField(max_length=255, blank=True)
    # TODO: GC?
    cover_image = models.ForeignKey(
        "media_service.Image", null=True, blank=True, on_delete=models.SET_NULL
    )

    # admin only?
    uploader_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True)
    uploader_id = models.PositiveIntegerField(null=True)
    uploader = GenericForeignKey("uploader_type", "uploader_id")

    external_ids = models.JSONField(default=dict, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    metadata_version = models.PositiveIntegerField(default=0)

    @property
    def bitrate(self):
        return self.resource.bitrate


# TODO: GC (7 days?)
# export music file with all metadata
class MusicExport(BaseModel):
    music = models.ForeignKey(Music, on_delete=models.CASCADE)

    # exported file, not MusicResource
    file = models.FileField(upload_to=music_upload_path)

    @property
    def metadata_version(self):
        return self.music.metadata_version
