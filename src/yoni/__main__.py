"""נקודת הכניסה של החבילה:  python -m yoni

בזכות זה אין קובץ הרצה בשורש הפרויקט. השורש מכיל את הפרויקט - לא סקריפטים
שכל תפקידם לתקן sys.path.
"""

import sys

from yoni.interfaces.cli.app import main

if __name__ == "__main__":
    sys.exit(main())
