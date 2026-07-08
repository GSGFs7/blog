import logging
import os

from django.test.runner import DiscoverRunner


class QuietTestRunner(DiscoverRunner):
    """Test runner that suppresses noisy log output during tests."""

    def setup_test_environment(self, **kwargs):
        """Set up test environment with quiet logging."""
        super().setup_test_environment(**kwargs)

        # Set root logger to WARNING level
        logging.getLogger().setLevel(logging.WARNING)

        # Disable specific loggers that produce noisy output
        logger_configs = {
            "jieba": logging.WARNING,
            "sentence_transformers": logging.WARNING,
            "transformers": logging.WARNING,
            "huggingface_hub": logging.WARNING,
            "urllib3": logging.WARNING,
            "requests": logging.WARNING,
            "PIL": logging.WARNING,
            "markdown": logging.WARNING,
            "api.signals": logging.CRITICAL,  # Suppress markdown conversion errors
            "api.tasks": logging.WARNING,
            "api.ml_model": logging.WARNING,
            "api.markdown": logging.WARNING,
            "celery": logging.WARNING,
            "django_celery_beat": logging.WARNING,
            "django.request": logging.CRITICAL,  # Suppress Unauthorized messages
            "django.security.csrf": logging.CRITICAL,  # Suppress CSRF
            "django.db.backends": logging.WARNING,
            "api.exiftool": logging.CRITICAL,  # Suppress ExifTool error messages
        }
        for name, level in logger_configs.items():
            logger = logging.getLogger(name)
            logger.setLevel(level)
            logger.propagate = False

        # Set environment variables to suppress framework logs
        os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
        os.environ["TRANSFORMERS_VERBOSITY"] = "error"
        os.environ["TOKENIZERS_PARALLELISM"] = "false"

        # Try to configure jieba logging if available
        try:
            import jieba

            # jieba may have setLogLevel attribute
            if hasattr(jieba, "setLogLevel"):
                jieba.setLogLevel(logging.WARNING)
        except ImportError, AttributeError:
            # jieba is optional or may not support setLogLevel;
            # ignore if configuration fails.
            logging.getLogger(__name__).debug(
                "Could not configure jieba logging; "
                "proceeding without jieba-specific log settings."
            )

    def teardown_test_environment(self, **kwargs):
        """Restore logging configuration after tests."""
        # Restore root logger level to INFO (default)
        logging.getLogger().setLevel(logging.INFO)

        # Re-enable propagation for noisy loggers
        noisy_loggers = [
            "jieba",
            "sentence_transformers",
            "transformers",
            "huggingface_hub",
            "urllib3",
            "requests",
            "PIL",
            "markdown",
            "api.signals",
            "api.tasks",
            "api.ml_model",
            "api.markdown",
            "celery",
            "django_celery_beat",
            "django.request",
            "django.security.csrf",
            "django.db.backends",
            "api.exiftool",
        ]
        for name in noisy_loggers:
            logger = logging.getLogger(name)
            logger.setLevel(logging.NOTSET)
            logger.propagate = True

        # Clean up environment variables
        os.environ.pop("TF_CPP_MIN_LOG_LEVEL", None)
        os.environ.pop("TRANSFORMERS_VERBOSITY", None)
        os.environ.pop("TOKENIZERS_PARALLELISM", None)

        super().teardown_test_environment(**kwargs)
