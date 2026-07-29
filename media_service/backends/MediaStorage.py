from storages.backends.s3 import S3Storage

IMMUTABLE_CACHE_CONTROL = "public, max-age=31536000, immutable"
DERIVED_CACHE_CONTROL = "public, max-age=604800"


class MediaStorage(S3Storage):
    def get_object_parameters(self, name: str):
        parameters = super().get_object_parameters(name)

        # add cache control header to R2 metadata
        if name.startswith(("images/raw/", "musics/")):
            # hash indexed image. cache it as long as possible
            parameters["CacheControl"] = IMMUTABLE_CACHE_CONTROL
        elif name.startswith(
            (
                "images/avif/",
                "images/webp/",
                "images/thumbnails/",
                "images/responsive/",
            )
        ):
            parameters["CacheControl"] = DERIVED_CACHE_CONTROL

        return parameters
