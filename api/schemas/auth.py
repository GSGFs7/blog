from ninja import Schema


class OAuthProviderSchema(Schema):
    provider_key: str
    name: str


class OAuthSessionSchema(Schema):
    identity_id: int
    guest_id: int
    provider_key: str
    user_id: str
    name: str
    email: str
    avatar: str
