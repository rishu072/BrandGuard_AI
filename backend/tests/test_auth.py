from datetime import timedelta
import uuid

from app.auth import AuthStore, hash_password, otp_hash, password_is_strong, utcnow, verify_password


def test_password_hashing_and_policy():
    stored = hash_password("SecureTest123!")
    assert stored != "SecureTest123!"
    assert verify_password(stored, "SecureTest123!")
    assert not verify_password(stored, "WrongPassword123!")
    assert password_is_strong("SecureTest123!")
    assert not password_is_strong("short")


def test_otp_is_hashed_expires_and_can_only_be_used_once():
    store = AuthStore()
    email = f"otp-{uuid.uuid4().hex}@example.com"
    code = "123456"
    hashed = otp_hash(email, "login", code)
    store.put_challenge({
        "email": email,
        "purpose": "login",
        "code_hash": hashed,
        "attempts": 0,
        "created_at": utcnow(),
        "expires_at": utcnow() + timedelta(minutes=5),
    })
    assert store.get_challenge(email, "login")["code_hash"] != code
    assert store.verify_challenge(email, "login", otp_hash(email, "login", code)) == (True, "ok")
    assert store.verify_challenge(email, "login", otp_hash(email, "login", code)) == (False, "missing")

    expired_email = f"expired-{uuid.uuid4().hex}@example.com"
    store.put_challenge({
        "email": expired_email,
        "purpose": "login",
        "code_hash": otp_hash(expired_email, "login", code),
        "attempts": 0,
        "created_at": utcnow() - timedelta(minutes=20),
        "expires_at": utcnow() - timedelta(minutes=10),
    })
    assert store.verify_challenge(expired_email, "login", otp_hash(expired_email, "login", code)) == (False, "expired")


def test_otp_attempt_cap_and_resend_cooldown():
    store = AuthStore()
    email = f"limited-{uuid.uuid4().hex}@example.com"
    store.put_challenge({
        "email": email,
        "purpose": "login",
        "code_hash": otp_hash(email, "login", "123456"),
        "attempts": 0,
        "created_at": utcnow(),
        "expires_at": utcnow() + timedelta(minutes=5),
    })
    for _ in range(5):
        assert store.verify_challenge(email, "login", otp_hash(email, "login", "000000"))[0] is False
    assert store.verify_challenge(email, "login", otp_hash(email, "login", "123456")) == (False, "locked")
    store.record_otp_send(email)
    allowed, retry_after = store.otp_send_allowed(email)
    assert not allowed
    assert retry_after > 0
