# import json
#
# from django.test import TestCase, override_settings
#
# from api.auth import TimeBaseAuth
# from api.models import Guest
#
#
# @override_settings(SECURE_SSL_REDIRECT=False)
# class TestGuest(TestCase):
#     def setUp(self) -> None:
#         return super().setUp()
#
#     def test_new_guest_login(self) -> None:
#         data = {
#             "name": "guest-test",
#             "avatar": "https://img.gsgfs.moe/img/1b987606005d9dc83312b987bad854a6.jpg",
#             "provider": "myself",
#             "provider_id": 1145,
#         }
#
#         response = self.client.post(
#             "/api/guest/login", data=json.dumps(data), content_type="application/json"
#         )
#         self.assertEqual(response.status_code, 401)
#
#         token = TimeBaseAuth.create_token("test_guest")
#         response = self.client.post(
#             "/api/guest/login",
#             data=json.dumps(data),
#             content_type="application/json",
#             HTTP_AUTHORIZATION=f"Bearer {token}",
#         )
#         self.assertEqual(response.status_code, 200)
#         response_data = json.loads(response.content)
#         latest_guest = Guest.objects.latest("id")
#         self.assertEqual(response_data["id"], latest_guest.pk)
