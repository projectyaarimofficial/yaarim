"""גדר הכתיבה - האכיפה בקוד של כלל 1 בחוקה.

עכשיו זו מדיניות מוזרקת, ולכן אפשר לבדוק אותה מול שורש זמני במקום מול הפרויקט.
"""

import os
import shutil
import tempfile
import unittest

from yoni.domain.ports import WriteDenied
from yoni.infrastructure.security.paths import ProjectWritePolicy, ReadOnlyWritePolicy


class PolicyTestCase(unittest.TestCase):
    def setUp(self):
        self.root = os.path.realpath(tempfile.mkdtemp())
        os.makedirs(os.path.join(self.root, "src", "yoni"), exist_ok=True)
        with open(os.path.join(self.root, "src", "yoni", "existing.py"), "w") as f:
            f.write("# existing\n")
        self.policy = ProjectWritePolicy(self.root)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)


class TestAllowed(PolicyTestCase):
    def test_relative_path_inside_project(self):
        self.assertEqual(
            self.policy.resolve("src/yoni/new.py"),
            os.path.join(self.root, "src", "yoni", "new.py"),
        )

    def test_existing_file(self):
        self.assertTrue(self.policy.resolve("src/yoni/existing.py").startswith(self.root))

    def test_absolute_path_inside_project(self):
        target = os.path.join(self.root, "src", "x.py")
        self.assertEqual(self.policy.resolve(target), target)

    def test_new_nested_directory(self):
        self.assertTrue(self.policy.resolve("a/b/c/deep.py").startswith(self.root))

    def test_root_itself(self):
        self.assertEqual(self.policy.resolve("."), self.root)

    def test_symlink_pointing_inside_is_allowed(self):
        os.symlink(os.path.join(self.root, "src"), os.path.join(self.root, "alias"))
        self.assertTrue(self.policy.resolve("alias/yoni/existing.py").startswith(self.root))


class TestDenied(PolicyTestCase):
    def test_parent_traversal(self):
        with self.assertRaises(WriteDenied):
            self.policy.resolve("../../../etc/passwd")

    def test_traversal_hidden_mid_path(self):
        with self.assertRaises(WriteDenied):
            self.policy.resolve("src/../../outside.py")

    def test_absolute_path_outside(self):
        with self.assertRaises(WriteDenied):
            self.policy.resolve("/etc/passwd")

    def test_home_dotfile(self):
        # התרחיש האמיתי: תוכנית הזויה שמכוונת לקובץ הגדרות של המשתמש.
        with self.assertRaises(WriteDenied):
            self.policy.resolve(os.path.expanduser("~/.zshrc"))

    def test_symlink_escaping_outside(self):
        outside = os.path.realpath(tempfile.mkdtemp())
        try:
            os.symlink(outside, os.path.join(self.root, "escape"))
            with self.assertRaises(WriteDenied):
                self.policy.resolve("escape/evil.py")
        finally:
            shutil.rmtree(outside, ignore_errors=True)

    def test_sibling_with_shared_prefix(self):
        # /x/proj מול /x/proj-evil: השוואת מחרוזות תמימה הייתה נכשלת כאן.
        sibling = self.root + "-evil"
        os.makedirs(sibling, exist_ok=True)
        try:
            with self.assertRaises(WriteDenied):
                self.policy.resolve(os.path.join(sibling, "x.py"))
        finally:
            shutil.rmtree(sibling, ignore_errors=True)

    def test_empty_values(self):
        for value in ("", "   ", None):
            with self.assertRaises(WriteDenied):
                self.policy.resolve(value)


class TestPolymorphism(PolicyTestCase):
    def test_read_only_policy_denies_everything(self):
        """אותו פורט, מדיניות אחרת - בלי לגעת בשירות שמשתמש בה."""
        policy = ReadOnlyWritePolicy()
        with self.assertRaises(WriteDenied):
            policy.resolve("src/yoni/perfectly_fine.py")

    def test_is_allowed_does_not_raise(self):
        self.assertTrue(self.policy.is_allowed("src/ok.py"))
        self.assertFalse(self.policy.is_allowed("../../etc/passwd"))


if __name__ == "__main__":
    unittest.main()
