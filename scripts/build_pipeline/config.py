IMAGES: tuple[tuple[str, str, str | None], ...] = (
    ("blog-app", ".config/k8s/containers/app.Dockerfile", None),
    ("blog-backup", ".config/k8s/containers/backup.Dockerfile", None),
    (
        "blog-model-downloader",
        ".config/k8s/containers/model-downloader.Dockerfile",
        None,
    ),
)
