#!/usr/bin/env python

"""
a lightweight ping celery app
"""

import os
import sys

from celery import Celery

broker = os.environ.get("REDIS_URL") or (
    f"redis://{os.environ.get('REDIS_HOST', 'blog-redis')}:"
    f"{os.environ.get('REDIS_PORT', '6379')}/0"
)
node = f"celery@{os.environ['HOSTNAME']}"

with Celery("healthcheck", broker=broker, fixups=[]) as app:
    replies = app.control.inspect(
        destination=[node],
        timeout=3,
        limit=1,
    ).ping()

sys.exit(0 if replies and replies.get(node, {}).get("ok") == "pong" else 1)
