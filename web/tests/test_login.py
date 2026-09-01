from django.contrib.auth import SESSION_KEY, get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import resolve, reverse

from accounts.services.login_flow import PREAUTH_SESSION_KEY
from api.models import Guest, OAuthIdentity, OAuthProvider
from api.services.oauth_session import (
    OAUTH_FLOW_SESSION_KEY,
    OAUTH_IDENTITY_SESSION_KEY,
)
from web.views import auth

TEST_CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "unified-login-tests",
    },
    "image_metadata": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "unified-login-image-metadata-tests",
    },
}


@override_settings(
    CACHES=TEST_CACHES,
    SECURE_SSL_REDIRECT=False,
    LOGIN_REDIRECT_URL="admin:index",
)
class UnifiedLoginTests(TestCase):
    def setUp(self):
        cache.clear()
        self.provider = OAuthProvider.objects.create(
            provider_key="example",
            name="Example OAuth",
            client_id="client-id",
            client_secret="client-secret",
            authorization_url="https://oauth.example/authorize",
            token_url="https://oauth.example/token",
            userinfo_url="https://oauth.example/user",
        )

    def test_canonical_routes_use_auth_views(self):
        self.assertIs(resolve(reverse("login")).func, auth.login)
        self.assertIs(resolve(reverse("admin_login")).func, auth.admin_login)
        self.assertIs(resolve(reverse("logout")).func, auth.logout)

    def test_login_endpoints_have_separate_methods(self):
        self.assertEqual(self.client.post(reverse("login")).status_code, 405)
        self.assertEqual(self.client.get(reverse("admin_login")).status_code, 405)

    def test_page_exposes_admin_and_active_oauth_branches(self):
        OAuthProvider.objects.create(
            provider_key="inactive",
            name="Inactive OAuth",
            client_id="client-id",
            client_secret="client-secret",
            authorization_url="https://inactive.example/authorize",
            token_url="https://inactive.example/token",
            userinfo_url="https://inactive.example/user",
            is_active=False,
        )

        response = self.client.get(reverse("login"), {"next": "/blog"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Admin login")
        self.assertContains(response, "Login with Example OAuth")
        self.assertNotContains(response, "Inactive OAuth")
        content = response.content.decode()
        self.assertLess(
            content.index('aria-label="OAuth login"'),
            content.index('id="admin-login-heading"'),
        )
        self.assertContains(response, '<details class="group mt-10">')
        self.assertNotContains(response, '<details class="group mt-10" open>')
        self.assertContains(response, f'action="{reverse("admin_login")}"')
        oauth_path = reverse(
            "api:oauth_login",
            kwargs={"provider_key": self.provider.provider_key},
        )
        self.assertContains(response, f"{oauth_path}?return_to=/blog")

    def test_non_staff_password_login_is_rejected(self):
        visitor = get_user_model().objects.create_user(
            username="visitor",
            password="correct-password",
        )

        response = self.client.post(
            reverse("admin_login"),
            {"username": visitor.username, "password": "correct-password"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Username or password incorrect.")
        self.assertContains(response, '<details class="group mt-10" open>')
        self.assertNotIn(SESSION_KEY, self.client.session)
        self.assertNotIn(PREAUTH_SESSION_KEY, self.client.session)

    def test_staff_password_login_replaces_oauth_identity(self):
        staff = get_user_model().objects.create_user(
            username="admin",
            password="correct-password",
            is_staff=True,
        )
        identity = self._create_identity()
        session = self.client.session
        session[OAUTH_IDENTITY_SESSION_KEY] = identity.pk
        session.save()

        response = self.client.post(
            reverse("admin_login"),
            {"username": staff.username, "password": "correct-password"},
        )

        self.assertRedirects(
            response,
            reverse("accounts:setup"),
            fetch_redirect_response=False,
        )
        self.assertNotIn(OAUTH_IDENTITY_SESSION_KEY, self.client.session)
        self.assertNotIn(SESSION_KEY, self.client.session)
        self.assertEqual(
            self.client.session[PREAUTH_SESSION_KEY]["user_id"],
            str(staff.pk),
        )
        self.assertEqual(
            self.client.session[PREAUTH_SESSION_KEY]["next"],
            reverse("admin:index"),
        )

    def test_staff_password_login_replaces_non_staff_django_session(self):
        visitor = get_user_model().objects.create_user(
            username="visitor",
            password="visitor-password",
        )
        staff = get_user_model().objects.create_user(
            username="admin",
            password="correct-password",
            is_staff=True,
        )
        self.client.force_login(visitor)

        response = self.client.post(
            reverse("admin_login"),
            {"username": staff.username, "password": "correct-password"},
        )

        self.assertRedirects(
            response,
            reverse("accounts:setup"),
            fetch_redirect_response=False,
        )
        self.assertNotIn(SESSION_KEY, self.client.session)
        self.assertEqual(
            self.client.session[PREAUTH_SESSION_KEY]["user_id"],
            str(staff.pk),
        )

    def test_admin_destination_is_not_used_as_oauth_return_url(self):
        response = self.client.get(reverse("login"), {"next": "/not-admin/"})

        oauth_path = reverse(
            "api:oauth_login",
            kwargs={"provider_key": self.provider.provider_key},
        )
        self.assertContains(response, f"{oauth_path}?return_to=/")

    def test_page_displays_oauth_identity_and_callback_error(self):
        identity = self._create_identity()
        session = self.client.session
        session[OAUTH_IDENTITY_SESSION_KEY] = identity.pk
        session.save()

        response = self.client.get(
            reverse("login"),
            {"oauth_error": "session_expired"},
        )

        self.assertContains(response, identity.guest.name)
        self.assertContains(response, "The OAuth login session expired")

    def test_unified_logout_clears_both_identity_types(self):
        staff = get_user_model().objects.create_user(
            username="admin",
            password="correct-password",
            is_staff=True,
        )
        identity = self._create_identity()
        self.client.force_login(staff)
        session = self.client.session
        session[OAUTH_IDENTITY_SESSION_KEY] = identity.pk
        session[OAUTH_FLOW_SESSION_KEY] = {"state": {"provider_key": "example"}}
        session.save()

        response = self.client.post(reverse("logout"))

        self.assertRedirects(
            response,
            reverse("index"),
            fetch_redirect_response=False,
        )
        self.assertNotIn(SESSION_KEY, self.client.session)
        self.assertNotIn(OAUTH_IDENTITY_SESSION_KEY, self.client.session)
        self.assertNotIn(OAUTH_FLOW_SESSION_KEY, self.client.session)

    def _create_identity(self):
        guest = Guest.objects.create(
            name="OAuth Visitor",
            email="visitor@example.com",
        )
        return OAuthIdentity.objects.create(
            guest=guest,
            provider=self.provider,
            user_id="provider-user-id",
        )
