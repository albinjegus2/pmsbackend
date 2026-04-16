from werkzeug.security import generate_password_hash, check_password_hash
from flask_jwt_extended import create_access_token, create_refresh_token
from datetime import timedelta


def hash_password(password: str) -> str:
    return generate_password_hash(password, method='pbkdf2:sha256', salt_length=16)


def verify_password(password: str, hashed: str) -> bool:
    return check_password_hash(hashed, password)


def generate_token(user_id: int, role: str) -> str:
    """Short-lived access token (8 hours)."""
    return create_access_token(
        identity=str(user_id),
        additional_claims={'role': role},
        expires_delta=timedelta(hours=8),
    )


def generate_refresh_token(user_id: int, role: str) -> str:
    """Long-lived refresh token (30 days)."""
    return create_refresh_token(
        identity=str(user_id),
        additional_claims={'role': role},
        expires_delta=timedelta(days=30),
    )
