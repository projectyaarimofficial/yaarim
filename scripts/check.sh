#!/usr/bin/env bash
# עטיפה דקה. הלוגיקה נמצאת ב-scripts/check.py כדי שתרוץ גם ב-Windows בלי bash.
exec python3 "$(dirname "$0")/check.py" "$@"
