from app.core.security import create_access_token, decode_access_token, hash_password, verify_password


def test_password_hash_and_verify():
    raw = "StrongPassword123!"
    hashed = hash_password(raw)
    assert hashed != raw
    assert verify_password(raw, hashed)
    assert not verify_password("wrong-password", hashed)


def test_jwt_roundtrip():
    token = create_access_token("user-1", "tenant-1", "admin")
    payload = decode_access_token(token)
    assert payload["sub"] == "user-1"
    assert payload["tenant_id"] == "tenant-1"
    assert payload["role"] == "admin"
