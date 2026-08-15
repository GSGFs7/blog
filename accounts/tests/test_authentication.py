from django.contrib import admin
from django.contrib.auth import SESSION_KEY, get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django_otp import DEVICE_ID_SESSION_KEY
from django_otp.oath import totp
from django_otp.plugins.otp_static.models import StaticDevice, StaticToken
from django_otp.plugins.otp_totp.models import TOTPDevice

from accounts.admin import TwoFactorAdminSite
from accounts.services.login_flow import (
    PREAUTH_SESSION_KEY,
    VERIFY_NEXT_SESSION_KEY,
)

TEST_CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "accounts-tests",
    }
}


@override_settings(
    CACHES=TEST_CACHES,
    SECURE_SSL_REDIRECT=False,
    LOGIN_REDIRECT_URL="admin:index",
)
class AuthenticationFlowTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(
            username="reader",
            password="correct-password",
            is_staff=True,
        )

    def test_staff_without_device_must_enroll_after_password(self):
        response = self.client.post(
            reverse("admin_login"),
            {"username": self.user.username, "password": "correct-password"},
        )

        self.assertRedirects(
            response,
            reverse("accounts:setup"),
            fetch_redirect_response=False,
        )
        self.assertIn(PREAUTH_SESSION_KEY, self.client.session)
        self.assertNotIn(SESSION_KEY, self.client.session)
        self.assertNotIn(DEVICE_ID_SESSION_KEY, self.client.session)

    def test_existing_totp_device_is_reused_without_migration(self):
        device = TOTPDevice.objects.create(
            user=self.user,
            name="default",
            confirmed=True,
        )

        response = self._password_login()
        self.assertRedirects(
            response,
            reverse("accounts:verify"),
            fetch_redirect_response=False,
        )
        self.assertNotIn(SESSION_KEY, self.client.session)

        response = self.client.post(
            reverse("accounts:verify"),
            {"device": device.persistent_id, "token": _current_token(device)},
        )

        self.assertRedirects(
            response,
            reverse("admin:index"),
            fetch_redirect_response=False,
        )
        self.assertEqual(self.client.session[SESSION_KEY], str(self.user.pk))
        self.assertEqual(
            self.client.session[DEVICE_ID_SESSION_KEY],
            device.persistent_id,
        )

    def test_totp_token_cannot_be_replayed(self):
        device = TOTPDevice.objects.create(
            user=self.user,
            name="default",
            confirmed=True,
        )
        token = _current_token(device)
        self._password_login()
        self.client.post(
            reverse("accounts:verify"),
            {"device": device.persistent_id, "token": token},
        )
        self.client.post(reverse("logout"))

        self._password_login()
        response = self.client.post(
            reverse("accounts:verify"),
            {"device": device.persistent_id, "token": token},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "The verification code is invalid, has been used, or is temporarily "
            "restricted",
        )
        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_recovery_code_is_consumed_once(self):
        TOTPDevice.objects.create(
            user=self.user,
            name="default",
            confirmed=True,
        )
        recovery_device = StaticDevice.objects.create(
            user=self.user,
            name="backup",
            confirmed=True,
        )
        recovery_token = StaticToken.objects.create(
            device=recovery_device,
            token="abcdefgh",
        )
        self._password_login()

        response = self.client.post(
            reverse("accounts:verify"),
            {"device": recovery_device.persistent_id, "token": "abcd-efgh"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(StaticToken.objects.filter(pk=recovery_token.pk).exists())
        self.assertEqual(
            self.client.session[DEVICE_ID_SESSION_KEY],
            recovery_device.persistent_id,
        )

    def test_existing_recovery_codes_are_preserved_during_totp_setup(self):
        recovery_device = StaticDevice.objects.create(
            user=self.user,
            name="backup",
            confirmed=True,
        )
        StaticToken.objects.bulk_create(
            [
                StaticToken(device=recovery_device, token="oldcode1"),
                StaticToken(device=recovery_device, token="oldcode2"),
            ]
        )
        self._password_login()
        self.client.post(
            reverse("accounts:verify"),
            {"device": recovery_device.persistent_id, "token": "oldcode1"},
        )
        self.client.get(reverse("accounts:setup"))
        device = TOTPDevice.objects.get(user=self.user, confirmed=False)

        response = self.client.post(
            reverse("accounts:setup"),
            {"token": _current_token(device)},
        )

        self.assertRedirects(
            response,
            reverse("admin:account_security"),
            fetch_redirect_response=False,
        )
        self.assertTrue(
            StaticToken.objects.filter(
                device=recovery_device, token="oldcode2"
            ).exists()
        )

    def test_expired_preauthentication_must_restart_login(self):
        device = TOTPDevice.objects.create(
            user=self.user,
            name="default",
            confirmed=True,
        )
        self._password_login()
        session = self.client.session
        preauth = session[PREAUTH_SESSION_KEY]
        preauth["created_at"] -= 301
        session[PREAUTH_SESSION_KEY] = preauth
        session.save()

        response = self.client.post(
            reverse("accounts:verify"),
            {"device": device.persistent_id, "token": _current_token(device)},
        )

        self.assertRedirects(
            response,
            reverse("login"),
            fetch_redirect_response=False,
        )
        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_external_next_url_is_rejected(self):
        response = self.client.post(
            f"{reverse('admin_login')}?next=https://attacker.example/",
            {
                "username": self.user.username,
                "password": "correct-password",
                "next": "https://attacker.example/",
            },
        )

        self.assertRedirects(
            response,
            reverse("accounts:setup"),
            fetch_redirect_response=False,
        )
        self.assertEqual(
            self.client.session[PREAUTH_SESSION_KEY]["next"],
            reverse("admin:index"),
        )

    def test_password_login_is_rate_limited(self):
        url = reverse("admin_login")
        for _ in range(5):
            self.client.post(
                url,
                {"username": self.user.username, "password": "wrong-password"},
            )

        response = self.client.post(
            url,
            {"username": self.user.username, "password": "correct-password"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Too many login attempts")
        self.assertNotIn(SESSION_KEY, self.client.session)

    @override_settings(
        TRUSTED_PROXY_CIDRS=("10.42.0.0/16",),
        LOGIN_THROTTLE_ACCOUNT_LIMIT=10,
        LOGIN_THROTTLE_ADDRESS_LIMIT=1,
    )
    def test_password_login_rate_limit_uses_cloudflare_client_ip(self):
        url = reverse("admin_login")
        proxy_headers = {"REMOTE_ADDR": "10.42.0.33"}
        self.client.post(
            url,
            {"username": self.user.username, "password": "wrong-password"},
            HTTP_CF_CONNECTING_IP="203.0.113.10",
            **proxy_headers,
        )

        response = self.client.post(
            url,
            {"username": self.user.username, "password": "correct-password"},
            HTTP_CF_CONNECTING_IP="203.0.113.11",
            **proxy_headers,
        )
        self.assertRedirects(
            response,
            reverse("accounts:setup"),
            fetch_redirect_response=False,
        )

        response = self.client.post(
            url,
            {"username": self.user.username, "password": "correct-password"},
            HTTP_CF_CONNECTING_IP="203.0.113.10",
            **proxy_headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Too many login attempts")

    def test_password_step_rotates_the_session_key(self):
        TOTPDevice.objects.create(
            user=self.user,
            name="default",
            confirmed=True,
        )
        session = self.client.session
        session["existing"] = True
        session.save()
        original_session_key = session.session_key

        self._password_login()

        self.assertNotEqual(self.client.session.session_key, original_session_key)

    def test_enabling_2fa_from_existing_session_requires_password(self):
        self.client.force_login(self.user)
        self.client.get(reverse("accounts:setup"))
        device = TOTPDevice.objects.get(user=self.user, confirmed=False)
        token = _current_token(device)

        response = self.client.post(
            reverse("accounts:setup"),
            {"token": token},
        )

        self.assertEqual(response.status_code, 200)
        device.refresh_from_db()
        self.assertFalse(device.confirmed)

        response = self.client.post(
            reverse("accounts:setup"),
            {"password": "correct-password", "token": token},
        )

        self.assertRedirects(
            response,
            reverse("admin:account_recovery_codes"),
            fetch_redirect_response=False,
        )
        device.refresh_from_db()
        self.assertTrue(device.confirmed)

    def test_non_staff_session_cannot_enter_two_factor_flow(self):
        user = get_user_model().objects.create_user(
            username="non-staff-user",
            password="correct-password",
        )
        self.client.force_login(user)

        setup_response = self.client.get(reverse("accounts:setup"))
        verify_response = self.client.get(reverse("accounts:verify"))

        self.assertRedirects(
            setup_response,
            reverse("login"),
            fetch_redirect_response=False,
        )
        self.assertRedirects(
            verify_response,
            reverse("login"),
            fetch_redirect_response=False,
        )
        self.assertFalse(TOTPDevice.objects.filter(user=user).exists())

    def _password_login(self):
        return self.client.post(
            reverse("admin_login"),
            {"username": self.user.username, "password": "correct-password"},
        )


@override_settings(
    CACHES=TEST_CACHES,
    SECURE_SSL_REDIRECT=False,
    LOGIN_REDIRECT_URL="admin:index",
)
class StaffEnrollmentTests(TestCase):
    def setUp(self):
        cache.clear()
        self.staff = get_user_model().objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="correct-password",
        )

    def test_staff_without_device_must_enroll_before_login(self):
        response = self.client.post(
            reverse("admin_login"),
            {
                "username": self.staff.username,
                "password": "correct-password",
                "next": reverse("admin:index"),
            },
        )

        self.assertRedirects(
            response,
            reverse("accounts:setup"),
            fetch_redirect_response=False,
        )
        self.assertNotIn(SESSION_KEY, self.client.session)

        setup_response = self.client.get(reverse("accounts:setup"))
        self.assertEqual(setup_response.status_code, 200)
        device = TOTPDevice.objects.get(user=self.staff, confirmed=False)

        qr_response = self.client.get(reverse("accounts:qr"))
        self.assertEqual(qr_response.status_code, 200)
        self.assertEqual(qr_response.headers["Content-Type"], "image/svg+xml")
        self.assertIn(b"<svg", qr_response.content)

        response = self.client.post(
            reverse("accounts:setup"),
            {"token": _current_token(device)},
        )

        self.assertRedirects(
            response,
            reverse("admin:account_recovery_codes"),
            fetch_redirect_response=False,
        )
        device.refresh_from_db()
        self.assertTrue(device.confirmed)
        self.assertEqual(self.client.session[SESSION_KEY], str(self.staff.pk))
        self.assertEqual(
            self.client.session[DEVICE_ID_SESSION_KEY],
            device.persistent_id,
        )
        self.assertEqual(
            StaticToken.objects.filter(device__user=self.staff).count(),
            10,
        )

        codes_response = self.client.get(reverse("admin:account_recovery_codes"))
        self.assertEqual(codes_response.status_code, 200)
        self.assertContains(codes_response, "Save recovery codes")
        self.assertContains(codes_response, reverse("admin:index"))
        self.assertEqual(
            self.client.head(reverse("admin:account_recovery_codes")).status_code,
            405,
        )

    def test_existing_device_requires_verification_before_setup(self):
        TOTPDevice.objects.create(
            user=self.staff,
            name="default",
            confirmed=True,
        )
        self.client.force_login(self.staff)

        setup_response = self.client.get(reverse("accounts:setup"))

        self.assertRedirects(
            setup_response,
            reverse("accounts:verify"),
            fetch_redirect_response=False,
        )
        self.assertEqual(
            self.client.session[VERIFY_NEXT_SESSION_KEY],
            reverse("accounts:setup"),
        )
        self.assertEqual(self.client.get(reverse("accounts:qr")).status_code, 403)

    def test_admin_and_api_docs_require_verified_session(self):
        device = TOTPDevice.objects.create(
            user=self.staff,
            name="default",
            confirmed=True,
        )
        self.client.force_login(self.staff)

        admin_response = self.client.get(reverse("admin:index"))
        security_response = self.client.get(reverse("admin:account_security"))
        docs_response = self.client.get("/api/docs")

        self.assertEqual(admin_response.status_code, 302)
        self.assertEqual(security_response.status_code, 302)
        admin_login_response = self.client.get(admin_response.url)
        self.assertEqual(admin_login_response.status_code, 302)
        self.assertIn(reverse("login"), admin_login_response.url)
        self.assertEqual(docs_response.status_code, 302)
        self.assertIn(reverse("login"), docs_response.url)

        _mark_client_verified(self.client, device)
        self.assertEqual(self.client.get(reverse("admin:index")).status_code, 200)
        self.assertEqual(self.client.get("/api/docs").status_code, 200)

    def test_project_uses_custom_admin_site(self):
        self.assertIsInstance(admin.site, TwoFactorAdminSite)

    def test_admin_includes_account_security_link(self):
        device = TOTPDevice.objects.create(
            user=self.staff,
            name="default",
            confirmed=True,
        )
        _mark_client_verified(self.client, device, self.staff)

        response = self.client.get(reverse("admin:index"))

        self.assertContains(response, reverse("admin:account_security"))
        self.assertContains(response, "Account security")


@override_settings(
    CACHES=TEST_CACHES,
    SECURE_SSL_REDIRECT=False,
    LOGIN_REDIRECT_URL="admin:index",
)
class SecurityManagementTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(
            username="security-user",
            password="correct-password",
            is_staff=True,
        )
        self.device = TOTPDevice.objects.create(
            user=self.user,
            name="default",
            confirmed=True,
        )
        self.recovery_device = StaticDevice.objects.create(
            user=self.user,
            name="backup",
            confirmed=True,
        )
        StaticToken.objects.create(device=self.recovery_device, token="oldcode1")
        _mark_client_verified(self.client, self.device, self.user)

    def test_regenerating_recovery_codes_invalidates_old_codes(self):
        response = self.client.post(
            reverse("admin:account_regenerate_recovery_codes"),
            {
                "password": "correct-password",
                "device": self.device.persistent_id,
                "token": _current_token(self.device),
            },
        )

        self.assertRedirects(
            response,
            reverse("admin:account_recovery_codes"),
            fetch_redirect_response=False,
        )
        self.assertFalse(StaticToken.objects.filter(token="oldcode1").exists())
        self.assertEqual(
            StaticToken.objects.filter(device__user=self.user).count(),
            10,
        )

    def test_replacing_authenticator_requires_password_and_current_factor(self):
        response = self.client.post(
            reverse("admin:account_replace_authenticator"),
            {
                "password": "correct-password",
                "device": self.device.persistent_id,
                "token": _current_token(self.device),
            },
        )

        self.assertRedirects(
            response,
            reverse("admin:account_replace_authenticator_setup"),
            fetch_redirect_response=False,
        )
        self.assertTrue(TOTPDevice.objects.filter(pk=self.device.pk).exists())
        replacement = TOTPDevice.objects.get(user=self.user, confirmed=False)

        setup_response = self.client.get(
            reverse("admin:account_replace_authenticator_setup")
        )
        self.assertEqual(setup_response.status_code, 200)
        self.assertContains(
            setup_response,
            reverse("admin:account_replace_authenticator_qr"),
        )

        response = self.client.post(
            reverse("admin:account_replace_authenticator_setup"),
            {"token": _current_token(replacement)},
        )

        self.assertRedirects(
            response,
            reverse("admin:account_security"),
            fetch_redirect_response=False,
        )
        self.assertFalse(TOTPDevice.objects.filter(pk=self.device.pk).exists())
        replacement.refresh_from_db()
        self.assertTrue(replacement.confirmed)
        self.assertEqual(
            self.client.session[DEVICE_ID_SESSION_KEY],
            replacement.persistent_id,
        )

    def test_invalid_replacement_code_keeps_old_authenticator(self):
        self.client.post(
            reverse("admin:account_replace_authenticator"),
            {
                "password": "correct-password",
                "device": self.device.persistent_id,
                "token": _current_token(self.device),
            },
        )

        response = self.client.post(
            reverse("admin:account_replace_authenticator_setup"),
            {"token": "000000"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(TOTPDevice.objects.filter(pk=self.device.pk).exists())

    def test_security_page_only_lists_current_users_devices(self):
        other = get_user_model().objects.create_user(
            username="other-admin",
            password="correct-password",
            is_staff=True,
        )
        TOTPDevice.objects.create(
            user=other,
            name="other-device",
            confirmed=True,
        )

        response = self.client.get(reverse("admin:account_security"))

        self.assertContains(response, self.device.name)
        self.assertNotContains(response, "other-device")

    def test_wrong_password_does_not_consume_otp(self):
        token = _current_token(self.device)
        response = self.client.post(
            reverse("admin:account_replace_authenticator"),
            {
                "password": "wrong-password",
                "device": self.device.persistent_id,
                "token": token,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.device.refresh_from_db()
        self.assertEqual(self.device.last_t, -1)


def _current_token(device):
    return str(
        totp(
            device.bin_key,
            step=device.step,
            t0=device.t0,
            digits=device.digits,
            drift=device.drift,
        )
    ).zfill(device.digits)


def _mark_client_verified(client, device, user=None):
    if user is not None:
        client.force_login(user)
    session = client.session
    session[DEVICE_ID_SESSION_KEY] = device.persistent_id
    session.save()
