"""Tests du jeton d'authentification (server/auth.py)."""
import unittest

from server import auth


class AuthTests(unittest.TestCase):
    def test_token_is_strong(self):
        # token_hex(16) → 32 caractères hex (128 bits)
        self.assertGreaterEqual(len(auth.TOKEN), 8)

    def test_valid_token_accepted(self):
        self.assertTrue(auth.validate(auth.TOKEN))

    def test_empty_rejected(self):
        self.assertFalse(auth.validate(''))

    def test_none_rejected(self):
        # `provided or ''` ne doit jamais lever sur None
        self.assertFalse(auth.validate(None))

    def test_wrong_token_rejected(self):
        self.assertFalse(auth.validate('deadbeef' * 4))

    def test_prefix_of_token_rejected(self):
        # Une comparaison naïve par préfixe passerait — compare_digest non.
        self.assertFalse(auth.validate(auth.TOKEN[:-1]))


if __name__ == '__main__':
    unittest.main()
