"""Tests for API key generation, hashing, and rotation."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import pytest

from forex_trading.shared.security.api_keys import (
    generate_api_key,
    verify_api_key,
    verify_api_key_with_rotation,
    rotate_api_key,
    hash_raw_key,
    is_valid_key_format,
    ApiKeyMaterial,
    RotatedKeySet,
    KEY_PREFIX,
    KEY_BYTE_LENGTH,
)


class TestGenerateApiKey:
    """Tests for API key generation."""

    def test_generate_returns_material(self):
        """generate_api_key should return ApiKeyMaterial with correct structure."""
        material = generate_api_key()
        assert isinstance(material, ApiKeyMaterial)
        assert material.raw_key.startswith(KEY_PREFIX)
        assert len(material.key_hash) == 64  # SHA-256 hex digest
        assert material.created_at is not None

    def test_generated_key_format(self):
        """Generated keys should match the fx_key_<hex> format."""
        material = generate_api_key()
        assert is_valid_key_format(material.raw_key) is True

    def test_generated_key_length(self):
        """Generated keys should have the correct total length."""
        material = generate_api_key()
        # KEY_PREFIX (6) + KEY_BYTE_LENGTH * 2 (64) = 70
        expected_len = len(KEY_PREFIX) + KEY_BYTE_LENGTH * 2
        assert len(material.raw_key) == expected_len

    def test_generated_keys_unique(self):
        """Each generated key should be unique."""
        key1 = generate_api_key()
        key2 = generate_api_key()
        assert key1.raw_key != key2.raw_key
        assert key1.key_hash != key2.key_hash


class TestVerifyApiKey:
    """Tests for API key verification."""

    def test_verify_valid_key(self):
        """A valid key should pass verification."""
        material = generate_api_key()
        assert verify_api_key(material.raw_key, material.key_hash) is True

    def test_verify_invalid_key(self):
        """An invalid key should fail verification."""
        material = generate_api_key()
        assert verify_api_key("invalid-key", material.key_hash) is False

    def test_verify_wrong_key(self):
        """A different key should fail verification."""
        m1 = generate_api_key()
        m2 = generate_api_key()
        assert verify_api_key(m1.raw_key, m2.key_hash) is False

    def test_verify_invalid_format(self):
        """A key with wrong format should fail."""
        assert verify_api_key("not-a-valid-key", "somehash") is False

    def test_verify_empty_key(self):
        """Empty key should fail."""
        assert verify_api_key("", "somehash") is False


class TestVerifyWithRotation:
    """Tests for rotation-aware verification."""

    def test_verify_primary_key(self):
        """Primary key should always work."""
        material = generate_api_key()
        rotated = RotatedKeySet(
            primary_hash=material.key_hash,
            secondary_hash=None,
            rotation_expires_at=None,
        )
        assert verify_api_key_with_rotation(
            material.raw_key,
            rotated.primary_hash,
            rotated.secondary_hash,
            rotated.rotation_expires_at,
        ) is True

    def test_verify_secondary_key_during_grace(self):
        """Secondary key should work during the grace period."""
        primary = generate_api_key()
        secondary = generate_api_key()
        future = datetime.now(timezone.utc) + timedelta(minutes=5)

        assert verify_api_key_with_rotation(
            secondary.raw_key,
            primary.key_hash,
            secondary.key_hash,
            future,
        ) is True

    def test_verify_secondary_key_after_grace(self):
        """Secondary key should fail after the grace period expires."""
        primary = generate_api_key()
        secondary = generate_api_key()
        past = datetime.now(timezone.utc) - timedelta(minutes=1)

        assert verify_api_key_with_rotation(
            secondary.raw_key,
            primary.key_hash,
            secondary.key_hash,
            past,
        ) is False

    def test_verify_none_key(self):
        """Both keys failing should return False."""
        material = generate_api_key()
        future = datetime.now(timezone.utc) + timedelta(minutes=5)
        assert verify_api_key_with_rotation(
            "wrong-key",
            material.key_hash,
            material.key_hash,
            future,
        ) is False


class TestRotateApiKey:
    """Tests for key rotation."""

    def test_rotate_returns_new_material_and_set(self):
        """rotate_api_key should return new material and a RotatedKeySet."""
        old = generate_api_key()
        new_material, rotated = rotate_api_key(old.key_hash)

        assert isinstance(new_material, ApiKeyMaterial)
        assert isinstance(rotated, RotatedKeySet)
        assert new_material.raw_key != old.raw_key
        assert rotated.primary_hash == new_material.key_hash
        assert rotated.secondary_hash == old.key_hash
        assert rotated.rotation_expires_at is not None

    def test_rotated_primary_key_works(self):
        """The new primary key should work immediately."""
        old = generate_api_key()
        new_material, rotated = rotate_api_key(old.key_hash)

        assert verify_api_key_with_rotation(
            new_material.raw_key,
            rotated.primary_hash,
            rotated.secondary_hash,
            rotated.rotation_expires_at,
        ) is True

    def test_rotated_secondary_key_works_during_grace(self):
        """The old key should still work during the grace period."""
        old = generate_api_key()
        new_material, rotated = rotate_api_key(old.key_hash)

        assert verify_api_key_with_rotation(
            old.raw_key,
            rotated.primary_hash,
            rotated.secondary_hash,
            rotated.rotation_expires_at,
        ) is True

    def test_rotate_custom_grace_period(self):
        """Rotation should accept a custom grace period."""
        old = generate_api_key()
        _, rotated = rotate_api_key(old.key_hash, grace_period_seconds=60)
        assert rotated.rotation_expires_at is not None
        remaining = (rotated.rotation_expires_at - datetime.now(timezone.utc)).total_seconds()
        assert remaining <= 61  # Allow 1 second tolerance


class TestHashRawKey:
    """Tests for hashing raw keys."""

    def test_hash_valid_key(self):
        """Hashing a valid key should produce a 64-char hex string."""
        material = generate_api_key()
        h = hash_raw_key(material.raw_key)
        assert len(h) == 64
        assert h == material.key_hash

    def test_hash_invalid_key_raises(self):
        """Hashing an invalid key format should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid API key format"):
            hash_raw_key("invalid-key")

    def test_hash_empty_key_raises(self):
        with pytest.raises(ValueError):
            hash_raw_key("")


class TestIsValidKeyFormat:
    """Tests for key format validation."""

    def test_valid_format(self):
        material = generate_api_key()
        assert is_valid_key_format(material.raw_key) is True

    def test_invalid_prefix(self):
        assert is_valid_key_format("bad_prefix_abcdef") is False

    def test_invalid_hex(self):
        assert is_valid_key_format("fx_key_zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz") is False

    def test_short_secret(self):
        assert is_valid_key_format("fx_key_abc") is False

    def test_empty_string(self):
        assert is_valid_key_format("") is False
