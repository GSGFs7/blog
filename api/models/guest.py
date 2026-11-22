import uuid

from django.db import models

from .base import BaseModel


class Guest(BaseModel):
    # prevent enumeration
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=50)
    email = models.EmailField()
    avatar = models.URLField(max_length=200)
    is_admin = models.BooleanField(default=False)
    last_visit = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name
