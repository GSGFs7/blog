from django.test import RequestFactory, SimpleTestCase, override_settings

from core.request import get_client_ip


@override_settings(TRUSTED_PROXY_CIDRS=("10.42.0.0/16", "fd00:42::/64"))
class ClientIPTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_uses_cloudflare_header_from_trusted_proxy(self):
        request = self.factory.get(
            "/",
            REMOTE_ADDR="10.42.0.33",
            HTTP_CF_CONNECTING_IP="203.0.113.10",
        )

        self.assertEqual(get_client_ip(request), "203.0.113.10")

    def test_prefers_original_ipv6_when_cloudflare_uses_pseudo_ipv4(self):
        request = self.factory.get(
            "/",
            REMOTE_ADDR="10.42.0.33",
            HTTP_CF_CONNECTING_IP="240.0.0.1",
            HTTP_CF_CONNECTING_IPV6="2001:db8::10",
        )

        self.assertEqual(get_client_ip(request), "2001:db8::10")

    def test_ignores_cloudflare_header_from_untrusted_peer(self):
        request = self.factory.get(
            "/",
            REMOTE_ADDR="198.51.100.20",
            HTTP_CF_CONNECTING_IP="203.0.113.10",
        )

        self.assertEqual(get_client_ip(request), "198.51.100.20")

    def test_trusted_proxy_without_valid_cloudflare_header_has_no_client_ip(self):
        request = self.factory.get(
            "/",
            REMOTE_ADDR="10.42.0.33",
            HTTP_CF_CONNECTING_IP="203.0.113.10, 198.51.100.20",
        )

        self.assertIsNone(get_client_ip(request))

    def test_supports_ipv6_proxy_addresses(self):
        request = self.factory.get(
            "/",
            REMOTE_ADDR="fd00:42::2",
            HTTP_CF_CONNECTING_IP="2001:db8::20",
        )

        self.assertEqual(get_client_ip(request), "2001:db8::20")
