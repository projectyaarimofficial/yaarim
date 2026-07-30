# עטיפה דקה ל-PowerShell. הלוגיקה נמצאת ב-scripts/check.py.
$python = if (Test-Path "$PSScriptRoot\..\.venv\Scripts\python.exe") {
    "$PSScriptRoot\..\.venv\Scripts\python.exe"
} else { "python" }
& $python "$PSScriptRoot\check.py" @args
exit $LASTEXITCODE
