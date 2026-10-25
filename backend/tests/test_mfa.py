"""Unit tests for verification codes, TOTP, recovery codes and the 2FA helpers.

No database or Redis required: users are transient ORM objects and Redis is a
small in-memory stand-in that implements only the commands the services use.
"""

from __future__ import annotations

import base64
import uuid
from datetime import UTC, datetime, timedelta

import pyotp
import pytest

from app.core.config import settings
from app.core.exceptions import AppError, AuthError, ConflictError, ForbiddenError
from app.core.security import create_mfa_token, decode_token, encrypt_pii, hash_password
from app.models.enums import MfaMethod, UserRole
from app.models.user import User
from app.schemas.user import UserRead
from app.services import mfa_service, otp_service, verification_service
from app.services.delivery import mask_email, mask_phone


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.ttls: dict[str, int] = {}

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None, nx: bool = False):
        if nx and key in self.store:
            return None
        self.store[key] = str(value)
        if ex is not None:
            self.ttls[key] = ex
        return True

    async def delete(self, *keys: str) -> int:
        removed = 0
        for key in keys:
            removed += int(self.store.pop(key, None) is not None)
            self.ttls.pop(key, None)
        return removed

    async def incr(self, key: str) -> int:
        value = int(self.store.get(key, "0")) + 1
        self.store[key] = str(value)
        return value

    async def expire(self, key: str, seconds: int) -> bool:
        self.ttls[key] = seconds
        return True

    async def ttl(self, key: str) -> int:
        return self.ttls.get(key, -1)

    async def exists(self, key: str) -> int:
        return int(key in self.store)


@pytest.fixture
def redis() -> FakeRedis:
    return FakeRedis()


def make_user(**overrides) -> User:
    fields = {
        "id": uuid.uuid4(),
        "email": "pat@example.com",
        "hashed_password": hash_password("Passw0rd!"),
        "first_name": "Pat",
        "last_name": "Lee",
        "phone": "+15551234567",
        "role": UserRole.customer,
        "is_active": True,
        "must_reset_password": False,
        "created_at": datetime.now(UTC),
    }
    fields.update(overrides)
    return User(**fields)


# --------------------------------------------------------------------------- #
# Delivery helpers                                                             #
# --------------------------------------------------------------------------- #
def test_masking_hides_most_of_the_destination() -> None:
    assert mask_email("pat@example.com") == "p**@example.com"
    assert mask_email("not-an-email") == "***"
    assert mask_phone("+1 (555) 123-4567") == "***-***-4567"
    assert mask_phone("12") == "***"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("(555) 123-4567", "+15551234567"),
        ("1-555-123-4567", "+15551234567"),
        ("+44 20 7946 0958", "+442079460958"),
    ],
)
def test_normalize_phone(raw: str, expected: str) -> None:
    assert verification_service.normalize_phone(raw) == expected


def test_normalize_phone_rejects_garbage() -> None:
    with pytest.raises(AppError) as exc:
        verification_service.normalize_phone("12345")
    assert exc.value.code == "INVALID_PHONE"


# --------------------------------------------------------------------------- #
# One-time codes                                                               #
# --------------------------------------------------------------------------- #
def test_generate_code_is_zero_padded_digits() -> None:
    codes = {otp_service.generate_code(6) for _ in range(50)}
    assert all(len(c) == 6 and c.isdigit() for c in codes)


async def test_otp_roundtrip_is_single_use(redis: FakeRedis) -> None:
    code = await otp_service.issue(
        redis, purpose="verify_email", subject="u1", destination="pat@example.com"
    )
    # Only a hash is stored, never the code itself.
    assert code not in "".join(redis.store.values())

    dest = await otp_service.verify(redis, purpose="verify_email", subject="u1", code=code)
    assert dest == "pat@example.com"
    with pytest.raises(AuthError) as exc:
        await otp_service.verify(redis, purpose="verify_email", subject="u1", code=code)
    assert exc.value.code == "CODE_EXPIRED"


async def test_otp_is_bound_to_purpose(redis: FakeRedis) -> None:
    code = await otp_service.issue(redis, purpose="login", subject="u1", destination="x")
    with pytest.raises(AuthError):
        await otp_service.verify(redis, purpose="verify_phone", subject="u1", code=code)


async def test_otp_attempts_are_limited(redis: FakeRedis) -> None:
    code = await otp_service.issue(redis, purpose="login", subject="u1", destination="x")
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(settings.OTP_MAX_ATTEMPTS):
        with pytest.raises(AuthError) as exc:
            await otp_service.verify(redis, purpose="login", subject="u1", code=wrong)
        assert exc.value.code == "INVALID_CODE"
    # Even the right code is refused once the budget is spent.
    with pytest.raises(AuthError) as exc:
        await otp_service.verify(redis, purpose="login", subject="u1", code=code)
    assert exc.value.code == "CODE_ATTEMPTS_EXCEEDED"


async def test_otp_resend_cooldown(redis: FakeRedis) -> None:
    await otp_service.issue(redis, purpose="login", subject="u1", destination="x")
    with pytest.raises(AppError) as exc:
        await otp_service.issue(redis, purpose="login", subject="u1", destination="x")
    assert exc.value.code == "CODE_RECENTLY_SENT"
    assert exc.value.status_code == 429


async def test_send_code_simulated_echoes_code(redis: FakeRedis) -> None:
    dispatch = await otp_service.send_code(
        redis, purpose="verify_phone", subject="u1", channel="sms", destination="+15551234567"
    )
    assert dispatch.simulated is True
    assert dispatch.destination == "***-***-4567"
    assert dispatch.simulated_code is not None
    dest = await otp_service.verify(
        redis, purpose="verify_phone", subject="u1", code=dispatch.simulated_code
    )
    assert dest == "+15551234567"


async def test_send_code_hides_code_when_echo_disabled(
    redis: FakeRedis, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "OTP_EXPOSE_SIMULATED_CODES", False)
    dispatch = await otp_service.send_code(
        redis, purpose="verify_email", subject="u1", channel="email", destination="a@b.com"
    )
    assert dispatch.simulated is True
    assert dispatch.simulated_code is None


# --------------------------------------------------------------------------- #
# Contact verification                                                         #
# --------------------------------------------------------------------------- #
async def test_phone_change_is_staged_until_confirmed(redis: FakeRedis) -> None:
    user = make_user(phone="555-000-1111")
    dispatch = await verification_service.send_phone_code(redis, user, "(555) 123-4567")
    # The number on file doesn't change until the code is confirmed.
    assert user.phone == "555-000-1111"
    assert dispatch.destination == "***-***-4567"


async def test_already_verified_email_cannot_resend(redis: FakeRedis) -> None:
    user = make_user(email_verified_at=datetime.now(UTC))
    with pytest.raises(ConflictError):
        await verification_service.send_email_code(redis, user)


def test_apply_phone_change_resets_verification() -> None:
    user = make_user(phone_verified_at=datetime.now(UTC))
    verification_service.apply_phone_change(user, "555-999-0000")
    assert user.phone == "555-999-0000"
    assert user.phone_verified_at is None


def test_apply_phone_change_ignores_reformatting() -> None:
    verified = datetime.now(UTC)
    user = make_user(phone="+15551234567", phone_verified_at=verified)
    verification_service.apply_phone_change(user, "(555) 123-4567")
    assert user.phone_verified_at == verified


def test_apply_phone_change_blocked_while_sms_is_second_factor() -> None:
    user = make_user(mfa_method=MfaMethod.sms, phone_verified_at=datetime.now(UTC))
    with pytest.raises(ConflictError) as exc:
        verification_service.apply_phone_change(user, "555-999-0000")
    assert exc.value.code == "PHONE_USED_FOR_MFA"


# --------------------------------------------------------------------------- #
# Recovery codes                                                               #
# --------------------------------------------------------------------------- #
def test_recovery_codes_format_and_uniqueness() -> None:
    codes = mfa_service.generate_recovery_codes(10)
    assert len(set(codes)) == 10
    for code in codes:
        assert len(code) == 11 and code[5] == "-"
        assert not set(code.replace("-", "")) & set("0o1li")
        assert mfa_service.looks_like_recovery_code(code)
    assert not mfa_service.looks_like_recovery_code("123456")


def test_recovery_code_consumed_once_and_case_insensitive() -> None:
    codes = mfa_service.generate_recovery_codes(3)
    user = make_user(mfa_recovery_codes=[mfa_service.hash_recovery_code(c) for c in codes])
    assert mfa_service.consume_recovery_code(user, codes[1].upper().replace("-", " "))
    assert len(user.mfa_recovery_codes or []) == 2
    assert not mfa_service.consume_recovery_code(user, codes[1])


# --------------------------------------------------------------------------- #
# TOTP                                                                         #
# --------------------------------------------------------------------------- #
def test_match_totp_allows_one_step_of_drift() -> None:
    secret = pyotp.random_base32()
    totp = pyotp.TOTP(secret)
    now = datetime(2026, 10, 24, 12, 0, 15, tzinfo=UTC)
    current = totp.timecode(now)

    assert mfa_service.match_totp(secret, totp.at(now), at=now) == current
    previous = totp.at(now - timedelta(seconds=30))
    assert mfa_service.match_totp(secret, previous, at=now) == current - 1
    stale = totp.at(now - timedelta(seconds=90))
    assert mfa_service.match_totp(secret, stale, at=now) is None
    assert mfa_service.match_totp(secret, "abcdef", at=now) is None


async def test_totp_code_cannot_be_replayed(redis: FakeRedis) -> None:
    secret = pyotp.random_base32()
    user = make_user(
        mfa_method=MfaMethod.totp, totp_secret_encrypted=encrypt_pii(secret)
    )
    code = pyotp.TOTP(secret).now()
    assert await mfa_service.verify_second_factor(redis, user, code) == "totp"
    with pytest.raises(AuthError):
        await mfa_service.verify_second_factor(redis, user, code)


def test_provisioning_uri_and_qr_code() -> None:
    uri = mfa_service.provisioning_uri("JBSWY3DPEHPK3PXP", "pat@example.com")
    assert uri.startswith("otpauth://totp/")
    assert "secret=JBSWY3DPEHPK3PXP" in uri
    assert f"issuer={settings.TOTP_ISSUER}" in uri

    data_uri = mfa_service.qr_code_data_uri(uri)
    prefix = "data:image/svg+xml;base64,"
    assert data_uri.startswith(prefix)
    svg = base64.b64decode(data_uri[len(prefix):]).decode()
    assert "<svg" in svg and "<path" in svg


async def test_totp_setup_requires_password_and_confirm_enables(
    redis: FakeRedis, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = make_user()
    with pytest.raises(AuthError):
        await mfa_service.begin_totp_setup(redis, user, "wrong")

    setup = await mfa_service.begin_totp_setup(redis, user, "Passw0rd!")
    assert setup.qr_code_data_uri.startswith("data:image/svg+xml")
    # Pending secret is stored encrypted, not in the clear.
    assert setup.secret not in "".join(redis.store.values())

    enabled: dict[str, object] = {}

    async def fake_enable(db, u, method):
        enabled["method"] = method
        return "ok"

    monkeypatch.setattr(mfa_service, "_enable", fake_enable)
    code = pyotp.TOTP(setup.secret).now()
    assert await mfa_service.confirm_totp_setup(None, redis, user, code) == "ok"  # type: ignore[arg-type]
    assert enabled["method"] == MfaMethod.totp
    assert user.totp_secret_encrypted and setup.secret not in user.totp_secret_encrypted


# --------------------------------------------------------------------------- #
# Email / SMS second factor                                                    #
# --------------------------------------------------------------------------- #
async def test_email_second_factor_roundtrip(redis: FakeRedis) -> None:
    user = make_user(mfa_method=MfaMethod.email, email_verified_at=datetime.now(UTC))
    dispatch = await mfa_service.send_login_code(redis, user)
    assert dispatch is not None and dispatch.channel == "email"
    assert dispatch.simulated_code is not None
    factor = await mfa_service.verify_second_factor(redis, user, dispatch.simulated_code)
    assert factor == "email"


async def test_switching_channel_sends_fresh_code(redis: FakeRedis) -> None:
    now = datetime.now(UTC)
    user = make_user(
        mfa_method=MfaMethod.sms, email_verified_at=now, phone_verified_at=now
    )
    sms = await mfa_service.send_login_code(redis, user)
    user.mfa_method = MfaMethod.email
    # Not blocked by the SMS resend cooldown, and the SMS code no longer works.
    email = await mfa_service.send_login_code(redis, user)
    assert email is not None and email.channel == "email"
    assert sms is not None and sms.simulated_code
    if sms.simulated_code != email.simulated_code:
        with pytest.raises(AuthError):
            await mfa_service.verify_second_factor(redis, user, sms.simulated_code)


async def test_send_login_code_is_noop_for_totp(redis: FakeRedis) -> None:
    user = make_user(mfa_method=MfaMethod.totp)
    assert await mfa_service.send_login_code(redis, user) is None


async def test_recovery_code_works_as_second_factor(redis: FakeRedis) -> None:
    codes = mfa_service.generate_recovery_codes(2)
    user = make_user(
        mfa_method=MfaMethod.totp,
        totp_secret_encrypted=encrypt_pii(pyotp.random_base32()),
        mfa_recovery_codes=[mfa_service.hash_recovery_code(c) for c in codes],
    )
    assert await mfa_service.verify_second_factor(redis, user, codes[0]) == "recovery"
    with pytest.raises(AuthError):
        await mfa_service.verify_second_factor(redis, user, codes[0])


# --------------------------------------------------------------------------- #
# Status, guards and tokens                                                    #
# --------------------------------------------------------------------------- #
def test_available_methods_follow_verified_channels() -> None:
    user = make_user()
    assert mfa_service.available_methods(user) == [MfaMethod.totp]
    user.email_verified_at = datetime.now(UTC)
    user.phone_verified_at = datetime.now(UTC)
    assert mfa_service.available_methods(user) == [
        MfaMethod.totp,
        MfaMethod.email,
        MfaMethod.sms,
    ]


async def test_enable_email_requires_verified_channel() -> None:
    user = make_user()
    with pytest.raises(ConflictError) as exc:
        await mfa_service.enable_otp_method(None, user, MfaMethod.email, "Passw0rd!")  # type: ignore[arg-type]
    assert exc.value.code == "CHANNEL_NOT_VERIFIED"


async def test_shared_demo_accounts_cannot_enable_mfa(
    redis: FakeRedis, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "DEMO_MODE_ENABLED", True)
    user = make_user(email="customer@insureco.com")
    assert mfa_service.build_status(user).mfa_locked_reason
    with pytest.raises(ForbiddenError):
        await mfa_service.begin_totp_setup(redis, user, "Passw0rd!")

    monkeypatch.setattr(settings, "DEMO_MODE_ENABLED", False)
    assert mfa_service.mfa_locked_reason(user) is None


def test_build_status_counts_recovery_codes() -> None:
    user = make_user(mfa_method=MfaMethod.sms, mfa_recovery_codes=["a", "b", "c"])
    status = mfa_service.build_status(user)
    assert status.mfa_enabled and status.mfa_method == MfaMethod.sms
    assert status.recovery_codes_remaining == 3


def test_user_read_exposes_flags_but_not_secrets() -> None:
    user = make_user(
        email_verified_at=datetime.now(UTC),
        mfa_method=MfaMethod.totp,
        totp_secret_encrypted="secret",
        mfa_recovery_codes=["hash"],
    )
    data = UserRead.model_validate(user).model_dump()
    assert data["email_verified"] is True
    assert data["phone_verified"] is False
    assert data["mfa_enabled"] is True
    assert "totp_secret_encrypted" not in data
    assert "mfa_recovery_codes" not in data


def test_mfa_token_has_its_own_type() -> None:
    payload = decode_token(create_mfa_token("user-1", {"method": "totp"}))
    assert payload["type"] == "mfa"
    assert payload["method"] == "totp"
    assert payload["jti"]
