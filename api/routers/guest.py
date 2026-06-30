# from ninja import Router
#
# from api.auth import AsyncTimeBaseAuth
# from api.models import Guest
# from api.schemas import GuestLoginSchema, GuestSchema, IdSchema, MessageSchema
#
# router = Router()
#
#
# @router.post("/login", response=IdSchema, auth=AsyncTimeBaseAuth())
# async def guest_login(request, body: GuestLoginSchema):
#     unique_id = f"{body.provider}-{body.provider_id}"
#
#     guest, created = await Guest.objects.aget_or_create(
#         unique_id=unique_id,
#         defaults={
#             "provider": body.provider,
#             "provider_id": body.provider_id,
#             "name": body.name,
#             "avatar": body.avatar,
#         },
#     )
#
#     # update user info
#     guest.avatar = body.avatar
#     guest.name = body.name
#     await guest.asave()
#
#     return guest
#
#
# @router.get(
#     "/{int:guest_id}",
#     response={200: GuestSchema, 404: MessageSchema},
#     auth=AsyncTimeBaseAuth(),
# )
# async def get_guest(request, guest_id: int):
#     try:
#         return await Guest.objects.aget(pk=guest_id)
#     except Guest.DoesNotExist:
#         return 404, {"message": "Not found"}
