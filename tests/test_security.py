import unittest

from app.security import create_access_token, decode_access_token, hash_password, verify_password


class SecurityTests(unittest.TestCase):
    def test_password_hash_verifies_without_storing_plaintext(self):
        password = "clinic-password-123"
        password_hash = hash_password(password)

        self.assertNotEqual(password, password_hash)
        self.assertTrue(verify_password(password, password_hash))
        self.assertFalse(verify_password("wrong-password", password_hash))

    def test_access_token_contains_user_id(self):
        token = create_access_token(42)

        self.assertEqual(decode_access_token(token), 42)
        self.assertIsNone(decode_access_token("invalid-token"))


if __name__ == "__main__":
    unittest.main()