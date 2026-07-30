"""גדר הכתיבה - מימוש WritePolicy.

זו האכיפה בקוד של כלל 1 בחוקה. עד שהוזרקה כפורט, הגבול היה קבוע בקוד; עכשיו
אפשר לבדוק אותו מול תיקייה זמנית, ואפשר להחליף מדיניות (למשל: לאסור כתיבה
לחלוטין) בלי לגעת בשירות שמשתמש בה.

בדיקה אחת על הנתיב *אחרי* נרמול ופתרון קישורים - כך גם "../.." וגם symlink
שמצביע החוצה נתפסים באותה נקודה, ואין מסלול שעוקף אחד מהם.
"""

import os
from typing import Optional


from ...domain.ports import WriteDenied, WritePolicy


def _existing_ancestor(path):
    """התיקייה הקיימת הקרובה ביותר בשרשרת ההורים (הקובץ עצמו עשוי להיות חדש)."""
    current = path
    while True:
        if os.path.exists(current):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return current
        current = parent


def _is_within(child, parent):
    """השוואה לפי רכיבי נתיב, לא לפי מחרוזת - כדי ש-'/x/proj-evil' לא ייחשב בתוך '/x/proj'."""
    try:
        return os.path.commonpath([child, parent]) == parent
    except ValueError:  # דיסקים שונים
        return False


class ProjectWritePolicy(WritePolicy):
    """מתירה כתיבה רק בתוך שורש נתון."""

    def __init__(self, root):
        self._root = os.path.realpath(root)

    @property
    def root(self) -> str:
        return self._root

    def resolve(self, target: Optional[str]) -> str:
        if not target or not str(target).strip():
            raise WriteDenied("לא צוין נתיב יעד.")

        target = str(target).strip()
        absolute = os.path.normpath(
            target if os.path.isabs(target) else os.path.join(self._root, target)
        )
        ancestor = _existing_ancestor(absolute)
        real_ancestor = os.path.realpath(ancestor)
        if absolute == ancestor:
            resolved = real_ancestor
        else:
            resolved = os.path.normpath(
                os.path.join(real_ancestor, os.path.relpath(absolute, ancestor))
            )

        if not _is_within(resolved, self._root):
            raise WriteDenied(f"נתיב היעד יוצא משורש הפרויקט ולכן נדחה: {target}")
        return resolved

    def is_allowed(self, target: Optional[str]) -> bool:
        try:
            self.resolve(target)
            return True
        except WriteDenied:
            return False


class ReadOnlyWritePolicy(WritePolicy):
    """אוסרת כל כתיבה. שימושית להרצה שבה /build מושבת לגמרי."""

    def resolve(self, target: Optional[str]) -> str:
        raise WriteDenied("הכתיבה מושבתת בתצורה הזו.")
