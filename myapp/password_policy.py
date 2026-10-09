import re

from django.core.exceptions import ValidationError


PASSWORD_POLICY_HELP = (
    "Password must be at least 8 characters long and include letters, numbers, and symbols."
)
PASSWORD_POLICY_ERROR = (
    "Password must be at least 8 characters long and include uppercase letters, "
    "lowercase letters, a number, and a special symbol."
)


def validate_strong_password(password, user=None):
    """Validate passwords only when a password is being created or changed."""
    value = str(password or "")
    if (
        len(value) < 8
        or not re.search(r"[A-Z]", value)
        or not re.search(r"[a-z]", value)
        or not re.search(r"\d", value)
        or not re.search(r"[^A-Za-z0-9]", value)
    ):
        raise ValidationError(PASSWORD_POLICY_ERROR)


class StrongPasswordValidator:
    """Django password-validator adapter for forms and built-in admin flows."""

    def validate(self, password, user=None):
        validate_strong_password(password, user)

    def get_help_text(self):
        return PASSWORD_POLICY_HELP
