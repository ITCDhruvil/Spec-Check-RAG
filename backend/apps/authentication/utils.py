import secrets
import string

MIN_PASSWORD_LENGTH = 10


def generate_password(length: int = 12) -> str:
    """Generate a secure password with at least MIN_PASSWORD_LENGTH characters."""
    length = max(length, MIN_PASSWORD_LENGTH)
    alphabet = string.ascii_letters + string.digits + "!@#$%&*"

    while True:
        password = "".join(secrets.choice(alphabet) for _ in range(length))
        if (
            any(c.islower() for c in password)
            and any(c.isupper() for c in password)
            and any(c.isdigit() for c in password)
        ):
            return password
