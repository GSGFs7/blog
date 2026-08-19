from .env import get_str

# resend email
RESEND_API_KEY = get_str("RESEND_API_KEY")
EMAIL_BACKEND = "api.backends.ResendEmailBackend"
DEFAULT_FROM_EMAIL = get_str("DEFAULT_FROM_EMAIL")
SERVER_EMAIL = get_str("DEFAULT_FROM_EMAIL")
ADMINS = [("admin", get_str("ADMIN_EMAIL"))]
