import re
from flask import request, jsonify
from functools import wraps


# ── Field validators ─────────────────────────────────────────

def is_valid_email(email: str) -> bool:
    return bool(re.match(r'^[^\s@]+@[^\s@]+\.[^\s@]+$', str(email).strip()))


def is_valid_date(value: str) -> bool:
    """Accepts YYYY-MM-DD."""
    return bool(re.match(r'^\d{4}-\d{2}-\d{2}$', str(value).strip()))


def is_valid_time(value: str) -> bool:
    """Accepts HH:MM or HH:MM:SS."""
    return bool(re.match(r'^\d{2}:\d{2}(:\d{2})?$', str(value).strip()))


def is_strong_password(password: str) -> bool:
    """Min 8 chars, at least one letter and one digit."""
    return len(password) >= 8 and bool(re.search(r'[A-Za-z]', password)) and bool(re.search(r'\d', password))


def sanitize_str(value, max_len: int = 500) -> str:
    """Strip whitespace and truncate."""
    return str(value).strip()[:max_len] if value is not None else ''


def validate_positive_int(value, name: str):
    """Return (int, None) or (None, error_str)."""
    try:
        v = int(value)
        if v <= 0:
            raise ValueError
        return v, None
    except (TypeError, ValueError):
        return None, f"{name} must be a positive integer"


def validate_range(value, min_val, max_val, name: str):
    try:
        v = float(value)
        if not (min_val <= v <= max_val):
            return None, f"{name} must be between {min_val} and {max_val}"
        return v, None
    except (TypeError, ValueError):
        return None, f"{name} must be a number"


# ── Decorator: require JSON body ─────────────────────────────

def require_json(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if request.method == 'OPTIONS':
            return f(*args, **kwargs)
        if not request.is_json:
            return jsonify({'error': 'Content-Type must be application/json'}), 415
        if request.content_length and request.content_length > 1 * 1024 * 1024:
            return jsonify({'error': 'Request body too large (max 1 MB)'}), 413
        return f(*args, **kwargs)
    return decorated


# ── Decorator: require specific roles ────────────────────────

def require_roles(*roles):
    from flask_jwt_extended import get_jwt, verify_jwt_in_request
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            verify_jwt_in_request()
            claims = get_jwt()
            if claims.get('role') not in roles:
                return jsonify({'error': 'Forbidden: insufficient role'}), 403
            return f(*args, **kwargs)
        return decorated
    return decorator
