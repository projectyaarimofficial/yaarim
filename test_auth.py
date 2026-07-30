# בדיקות אוטומטיות ל-yoni.auth (מסך ההתחברות). משתמש ב-DB זמני לכל בדיקה.

import os
import shutil
import tempfile
import unittest

from yoni import auth, config


class AuthTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="yoni_auth_test_")
        self.addCleanup(shutil.rmtree, self.tmp_dir, ignore_errors=True)

        original = {"DATA_DIR": config.DATA_DIR, "DB_PATH": config.DB_PATH}
        self.addCleanup(lambda: config.__dict__.update(original))
        config.DATA_DIR = os.path.join(self.tmp_dir, "data")
        config.DB_PATH = os.path.join(config.DATA_DIR, "yoni_memory.db")

        auth.init_db()


class TestAuth(AuthTestCase):
    def test_create_and_verify(self):
        auth.create_user("student1", "s3cret")
        self.assertTrue(auth.verify_user("student1", "s3cret"))

    def test_wrong_password_fails(self):
        auth.create_user("student1", "s3cret")
        self.assertFalse(auth.verify_user("student1", "wrong"))

    def test_unknown_user_fails(self):
        self.assertFalse(auth.verify_user("nobody", "whatever"))

    def test_password_not_stored_in_plaintext(self):
        auth.create_user("student1", "s3cret")
        with open(config.DB_PATH, "rb") as f:
            blob = f.read()
        self.assertNotIn(b"s3cret", blob)

    def test_duplicate_user_raises(self):
        auth.create_user("student1", "s3cret")
        with self.assertRaises(ValueError):
            auth.create_user("student1", "other")

    def test_empty_fields_raise(self):
        with self.assertRaises(ValueError):
            auth.create_user("", "pw")
        with self.assertRaises(ValueError):
            auth.create_user("id", "")

    def test_whitespace_id_is_normalized(self):
        auth.create_user("  student1  ", "s3cret")
        self.assertTrue(auth.verify_user("student1", "s3cret"))
        self.assertTrue(auth.user_exists("student1"))


if __name__ == "__main__":
    unittest.main()
