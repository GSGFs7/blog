from base64 import b64encode
from typing import Any, Iterable, Union

import httpx2
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend
from django.core.mail.message import EmailMessage, EmailMultiAlternatives


class ResendEmailBackend(BaseEmailBackend):
    def __init__(self, fail_silently=False, **kwargs):
        super().__init__(fail_silently, **kwargs)
        self.api_key = getattr(settings, "RESEND_API_KEY", "")

    def send_messages(self, email_messages: Iterable[EmailMessage]) -> int:
        """method of send email, will return the number of email was send"""
        if not email_messages:
            return 0

        count = 0
        for message in email_messages:
            sent = self._send(message)
            if sent:
                count += 1

        return count

    def _send(self, email_message: Union[EmailMessage, EmailMultiAlternatives]) -> bool:
        try:
            params: dict[str, Any] = {
                "from": email_message.from_email,
                "to": email_message.to,
                "subject": email_message.subject,
                "text": email_message.body,
            }

            if email_message.cc:
                params["cc"] = email_message.cc
            if email_message.bcc:
                params["bcc"] = email_message.bcc

            if email_message.attachments:
                attachments: list[dict[str, str]] = []
                for attachment in email_message.attachments:
                    if isinstance(attachment, tuple) and len(attachment) >= 2:
                        content = attachment[1]
                        if isinstance(content, str):
                            content = content.encode()
                        attach_data = {
                            "filename": attachment[0],
                            "content": b64encode(content).decode(),
                        }
                        attachments.append(attach_data)
                if attachments:
                    params["attachments"] = attachments

            response = httpx2.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=params,
            )
            response.raise_for_status()
            return "id" in response.json()
        except Exception:
            if not self.fail_silently:
                raise
            return False
