"""Test Encryption Utility."""
import os

from utils.encryption import encrypt, decrypt, encrypt_dict_values, decrypt_dict_values


class TestEncryption:
    def test_roundtrip(self):
        original = "my-secret-api-key-12345"
        encrypted = encrypt(original)
        assert encrypted != original
        decrypted = decrypt(encrypted)
        assert decrypted == original

    def test_empty_value(self):
        assert encrypt("") == ""
        assert decrypt("") == ""

    def test_dict_encryption(self):
        data = {"api_key": "sk-test123", "name": "visible"}
        encrypted = encrypt_dict_values(data, ["api_key"])
        assert encrypted["api_key"] != "sk-test123"
        assert encrypted["name"] == "visible"
        decrypted = decrypt_dict_values(encrypted, ["api_key"])
        assert decrypted["api_key"] == "sk-test123"

    def test_decrypt_plaintext_fallback(self):
        """If value was not encrypted, decrypt returns it as-is."""
        assert decrypt("plaintext-value") == "plaintext-value"

    def test_different_keys_produce_different_ciphertexts(self):
        original = "secret"
        e1 = encrypt(original)
        e2 = encrypt(original)
        assert e1 != e2  # nonce is random
        assert decrypt(e1) == original
        assert decrypt(e2) == original
