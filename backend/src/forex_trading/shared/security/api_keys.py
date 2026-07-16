"""API key generation, hashing, verification, and rotation.

API keys follow the format ``fx_key_<32-hex-chars>``.
Only SHA-256 hashes of the secret portion are stored in the database.
Supports rotation with a configurable grace period so both old and new
keys are accepted during the transition.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import ClassVar

import structlog

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

KEY_PREFIX = "fx_key_"
"""Prefix used for all generated API keys so they are easily identifiable."""

HASH_ALGORITHM = "sha256"
"""Hash algorithm used for storing API key digests."""

KEY_BYTE_LENGTH = 32
"""Random byte length of the key secret (64 hex chars after prefix)."""

_DEFAULT_GRACE_SECONDS = 300  # 5 minutes


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class ApiKeyMaterial:
    """The full material returned when creating a new API key.

    The ``raw_key`` value should be shown **exactly once** to the caller
    (e.g. in an API response).  It is never persisted.
    """

    raw_key: str
    """The full ``fx_key_<hex>`` string — show once, then discard."""

    key_hash: str
    """SHA-256 hex digest of the secret portion (store in DB)."""

    key_prefix: str
    """First 12 characters of the raw key (for log lookup)."""

    created_at: datetime
    """Timestamp of creation."""


@dataclass
class RotatedKeySet:
    """Represents a key pair during the rotation grace window.

    ``primary_hash`` is the hash of the **new** key.
    ``secondary_hash`` is the hash of the **old** key (still valid).
    """

    primary_hash: str
    secondary_hash: str | None
    rotation_expires_at: datetime | None


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------


def _extract_secret(raw_key: str) -> str:
    """Strip the prefix and return the hex secret portion."""
    if not raw_key.startswith(KEY_PREFIX):
        raise ValueError(f"API key must start with '{KEY_PREFIX}'")
    return raw_key[len(KEY_PREFIX):]


def _hash_secret(secret: str) -> str:
    """Return the SHA-256 hex digest of *secret*."""
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def generate_api_key() -> ApiKeyMaterial:
    """Generate a new API key with the ``fx_key_<hex>`` format.

    Returns
    -------
    ApiKeyMaterial
        Contains the full raw key (show once), the hash (persist),
        and metadata.
    """
    secret = secrets.token_hex(KEY_BYTE_LENGTH)  # 64 hex chars
    raw_key = f"{KEY_PREFIX}{secret}"
    key_hash = _hash_secret(secret)
    now = datetime.now(timezone.utc)

    logger.debug("api_key_generated", key_prefix=raw_key[: len(KEY_PREFIX) + 8])

    return ApiKeyMaterial(
        raw_key=raw_key,
        key_hash=key_hash,
        key_prefix=raw_key[: len(KEY_PREFIX) + 8],
        created_at=now,
    )


def verify_api_key(raw_key: str, stored_hash: str) -> bool:
    """Constant-time comparison of *raw_key* against *stored_hash*.

    Parameters
    ----------
    raw_key : str
        The full ``fx_key_<hex>`` string provided by the caller.
    stored_hash : str
        The SHA-256 hex digest stored in the database.

    Returns
    -------
    bool
        ``True`` if the key matches.
    """
    try:
        secret = _extract_secret(raw_key)
    except ValueError:
        return False
    computed = _hash_secret(secret)
    return hmac.compare_digest(computed, stored_hash)


def verify_api_key_with_rotation(
    raw_key: str,
    primary_hash: str,
    secondary_hash: str | None,
    rotation_expires_at: datetime | None,
) -> bool:
    """Check *raw_key* against both primary and (optionally) secondary hash.

    During a rotation grace period the old key is still accepted.
    """
    if verify_api_key(raw_key, primary_hash):
        return True
    if secondary_hash is not None and rotation_expires_at is not None:
        if datetime.now(timezone.utc) < rotation_expires_at:
            return verify_api_key(raw_key, secondary_hash)
    return False


def rotate_api_key(
    old_hash: str,
    grace_period_seconds: int = _DEFAULT_GRACE_SECONDS,
) -> tuple[ApiKeyMaterial, RotatedKeySet]:
    """Rotate an API key, returning the new material and a key set.

    The old key remains valid for *grace_period_seconds*.

    Parameters
    ----------
    old_hash : str
        The current hash stored in the database.
    grace_period_seconds : int
        How long the old key stays valid after rotation.

    Returns
    -------
    tuple[ApiKeyMaterial, RotatedKeySet]
        ``(new_key_material, rotated_key_set)``
    """
    new_key = generate_api_key()
    now = datetime.now(timezone.utc)
    rotated = RotatedKeySet(
        primary_hash=new_key.key_hash,
        secondary_hash=old_hash,
        rotation_expires_at=now + timedelta(seconds=grace_period_seconds),
    )
    logger.info(
        "api_key_rotated",
        key_prefix=new_key.key_prefix,
        grace_period_seconds=grace_period_seconds,
    )
    return new_key, rotated


def hash_raw_key(raw_key: str) -> str:
    """Utility to hash a raw key for storage (e.g. when saving a key)."""
    try:
        secret = _extract_secret(raw_key)
    except ValueError:
        raise ValueError(f"Invalid API key format: must start with '{KEY_PREFIX}'")
    return _hash_secret(secret)


def is_valid_key_format(raw_key: str) -> bool:
    """Check whether *raw_key* matches the expected ``fx_key_<hex>`` pattern."""
    if not raw_key.startswith(KEY_PREFIX):
        return False
    secret = raw_key[len(KEY_PREFIX):]
    if len(secret) != KEY_BYTE_LENGTH * 2:  # hex encoding doubles byte length
        return False
    try:
        int(secret, 16)
        return True
    except ValueError:
        return False
