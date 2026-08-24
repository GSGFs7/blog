from unittest.mock import patch

import httpx2
from django.core.mail import EmailMessage
from django.test import SimpleTestCase, override_settings

from api.backends import ResendEmailBackend


@override_settings(RESEND_API_KEY="re_test")
class ResendEmailBackendTest(SimpleTestCase):
    @patch("api.backends.resend_email.httpx2.post")
    def test_send_email_posts_resend_payload(self, post):
        post.return_value = httpx2.Response(
            200,
            json={"id": "email-id"},
            request=httpx2.Request("POST", "https://api.resend.com/emails"),
        )
        message = EmailMessage(
            subject="Subject",
            body="Body",
            from_email="Sender <sender@example.com>",
            to=["to@example.com"],
            cc=["cc@example.com"],
            bcc=["bcc@example.com"],
        )
        message.attach("report.txt", b"payload", "text/plain")

        sent = ResendEmailBackend().send_messages([message])

        self.assertEqual(sent, 1)
        post.assert_called_once_with(
            "https://api.resend.com/emails",
            headers={"Authorization": "Bearer re_test"},
            json={
                "from": "Sender <sender@example.com>",
                "to": ["to@example.com"],
                "subject": "Subject",
                "text": "Body",
                "cc": ["cc@example.com"],
                "bcc": ["bcc@example.com"],
                "attachments": [{"filename": "report.txt", "content": "cGF5bG9hZA=="}],
            },
        )
