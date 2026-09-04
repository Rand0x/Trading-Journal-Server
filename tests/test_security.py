"""Tests for security helpers that do not require a running web server."""

import base64
import unittest

from server.main import is_authorized


class TestBasicAuthentication(unittest.TestCase):
    def test_accepts_valid_basic_credentials(self):
        token = base64.b64encode(b"journal:correct-horse-battery-staple").decode()
        self.assertTrue(is_authorized(f"Basic {token}", ("journal", "correct-horse-battery-staple")))

    def test_rejects_missing_or_invalid_credentials(self):
        self.assertFalse(is_authorized(None, ("journal", "password")))
        self.assertFalse(is_authorized("Bearer token", ("journal", "password")))
        invalid = base64.b64encode(b"journal:wrong-password").decode()
        self.assertFalse(is_authorized(f"Basic {invalid}", ("journal", "password")))


if __name__ == "__main__":
    unittest.main()
