IMAGE_ALLOWED_FORMAT: set[str] = {
    "image/apng",  # Animated PNG
    "image/avif",  # AV1 encoded image
    "image/bmp",  # Windows bitmap image, uncompressed, needs convert
    # DNG??? Why don't you upload camera RAW files?
    # "image/DNG",
    "image/gif",
    # HEIC(a variant of HEIF, iPhone photo format): encoded by HEVC
    "image/heic",
    "image/heic-sequence",
    # HEIF: encoded by HEVC/AV1/JPEG
    "image/heif",
    "image/heif-sequence",
    # icon? does anyone actually use this?
    # "image/x-icon",
    "image/jpeg",
    "image/jxl",  # new JPEG
    "image/png",
    # SVG is text, maybe unsafe
    # "image/svg+xml",
    # TIFF: used by many photographers, very large
    # remember to convert to another format
    "image/tiff",
    "image/webp",
}

RESPONSIVE_IMAGE_WIDTHS = (320, 640, 1280, 1920)
