from .env import get_bool, get_int, get_str, is_docker_env

_DOCKER_ENV = is_docker_env()

_database_engine = get_str("DATABASE_ENGINE", "postgresql")
if _database_engine == "sqlite3":
    # build-time fallback (collect static)
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": ":memory:",
        }
    }
elif _database_engine == "postgresql":
    DATABASES = {
        "default": {
            "ENGINE": f"django_prometheus.db.backends.{_database_engine}",
            "NAME": get_str("DATABASE_NAME"),
            "USER": get_str("DATABASE_USER"),
            "PASSWORD": get_str("DATABASE_PASSWORD"),
            "HOST": get_str(
                "DATABASE_HOST",
                "blog-postgres" if _DOCKER_ENV else "127.0.0.1",
            ),
            "PORT": get_int("DATABASE_PORT", 5432),
            "CONN_MAX_AGE": get_int("DATABASE_CONN_MAX_AGE", 0),
            "CONN_HEALTH_CHECKS": get_bool("DATABASE_CONN_HEALTH_CHECKS", True),
            "DISABLE_SERVER_SIDE_CURSORS": get_bool("DATABASE_USE_PGBOUNCER"),
        }
    }
else:
    raise RuntimeError(f"Unsupported DATABASE_ENGINE: {_database_engine}")

_redis_host = get_str("REDIS_HOST", "localhost")
if _DOCKER_ENV:
    _redis_host = "blog-redis"
_redis_port = get_str("REDIS_PORT", "6379")
_redis_url = get_str("REDIS_URL", f"redis://{_redis_host}:{_redis_port}/0")
CACHES = {
    "default": {
        "BACKEND": "django_prometheus.cache.backends.redis.RedisCache",
        "LOCATION": _redis_url,
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            "CONNECTION_POOL_KWARGS": {"max_connections": 100},
        },
        "KEY_PREFIX": "django",  # eg. django:1:health_check
    },
    # this alias ignore exceptions
    "image_metadata": {
        "BACKEND": "django_prometheus.cache.backends.redis.RedisCache",
        "LOCATION": _redis_url,
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            "CONNECTION_POOL_KWARGS": {"max_connections": 100},
            "IGNORE_EXCEPTIONS": True,
        },
        "KEY_PREFIX": "image-metadata",
    },
}

SESSION_ENGINE = "django.contrib.sessions.backends.cache"
SESSION_CACHE_ALIAS = "default"
CACHE_TTL = 60 * 10

# Celery configuration
CELERY_BROKER_URL = _redis_url
CELERY_RESULT_BACKEND = _redis_url
CELERY_TIMEZONE = "Asia/Shanghai"
# Celery scheduled tasks use database storage,
# if hasn't set it django_celery_beat will not work
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
