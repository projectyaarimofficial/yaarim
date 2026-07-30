<#
.SYNOPSIS
    התקנה מלאה של יערים על Windows, בלי Docker.

.DESCRIPTION
    מתקין הכל מאפס ומריץ את האפליקציה:
      1. בודק Python 3.10+
      2. יוצר סביבה וירטואלית (.venv)
      3. מתקין את התלויות המקובעות
      4. בודק Ollama, ומתקין דרך winget אם חסר
      5. מריץ את שרת Ollama ומוריד את המודל
      6. מריץ את הבדיקות
      7. פותח את האפליקציה בדפדפן

    הרצה חוזרת בטוחה: מדלג על מה שכבר קיים.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\install.ps1

.NOTES
    אם PowerShell מסרב להריץ סקריפטים, זו הגדרת אבטחה של Windows ולא תקלה:
        Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#>

[CmdletBinding()]
param(
    [switch]$SkipModel,   # דלג על הורדת המודל (3.3GB)
    [switch]$NoLaunch     # התקן בלבד, בלי להריץ את האפליקציה
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
$RequiredModel = "gemma3:4b"

function Write-Step($n, $text) { Write-Host "`n[$n/7] $text" -ForegroundColor Cyan }
function Write-Ok($text)       { Write-Host "      ok   $text" -ForegroundColor Green }
function Write-Warn2($text)    { Write-Host "      warn $text" -ForegroundColor Yellow }
function Write-Fail($text)     { Write-Host "      FAIL $text" -ForegroundColor Red }

function Test-Command($name) {
    $null -ne (Get-Command $name -ErrorAction SilentlyContinue)
}

Write-Host "`n🧱 יערים (YAARIM) — התקנה ל-Windows" -ForegroundColor White
Write-Host "   שורש הפרויקט: $Root"

# ---------------------------------------------------------------------------
Write-Step 1 "בודק Python"
# ---------------------------------------------------------------------------
# מלכודת ידועה ב-Windows: קיים "python" מדומה מ-Microsoft Store שנמצא ב-PATH,
# עונה ל-Get-Command, אבל רק פותח את החנות. לכן לא מספיק לבדוק שהפקודה קיימת -
# צריך לוודא שהיא באמת מחזירה מספר גרסה.
$versionText = $null
if (Test-Command "python") {
    try { $versionText = (python --version 2>&1 | Out-String).Trim() } catch { }
}
$parsed = $null
if ($versionText -match "Python\s+(\d+\.\d+(\.\d+)?)") {
    $parsed = [version]$Matches[1]
}

if (-not $parsed) {
    Write-Fail "Python לא נמצא (או שמותקן רק ה-stub של Microsoft Store)."
    Write-Host "      התקן ונסה שוב:" -ForegroundColor Yellow
    Write-Host "        winget install Python.Python.3.12" -ForegroundColor Yellow
    Write-Host "      אם ההתקנה קיימת אך נפתחת חנות: Settings > Apps > App execution aliases" -ForegroundColor Yellow
    Write-Host "      וכבה שם את python.exe / python3.exe" -ForegroundColor Yellow
    exit 1
}
if ($parsed -lt [version]"3.10") {
    Write-Fail "נדרש Python 3.10 ומעלה. מותקן: $parsed"
    exit 1
}
Write-Ok "Python $parsed"

# ---------------------------------------------------------------------------
Write-Step 2 "סביבה וירטואלית"
# ---------------------------------------------------------------------------
if (Test-Path $VenvPython) {
    Write-Ok ".venv כבר קיימת"
} else {
    python -m venv (Join-Path $Root ".venv")
    if (-not (Test-Path $VenvPython)) { Write-Fail "יצירת .venv נכשלה"; exit 1 }
    Write-Ok ".venv נוצרה"
}

# ---------------------------------------------------------------------------
Write-Step 3 "תלויות"
# ---------------------------------------------------------------------------
& $VenvPython -m pip install --quiet --upgrade pip
& $VenvPython -m pip install --quiet -r (Join-Path $Root "requirements.txt")
if ($LASTEXITCODE -ne 0) { Write-Fail "התקנת התלויות נכשלה"; exit 1 }
Write-Ok "התלויות מותקנות (מקובעות ב-requirements.txt)"

# כלי פיתוח (mypy) - לא נדרשים להרצה, נדרשים לבדיקה. כישלון כאן אינו עוצר.
& $VenvPython -m pip install --quiet -r (Join-Path $Root "requirements-dev.txt") 2>$null
if ($LASTEXITCODE -eq 0) { Write-Ok "כלי פיתוח מותקנים (mypy)" }
else { Write-Warn2 "כלי הפיתוח לא הותקנו - הבדיקה תדלג על הטיפוסים" }

# ---------------------------------------------------------------------------
Write-Step 4 "Ollama"
# ---------------------------------------------------------------------------
if (Test-Command "ollama") {
    Write-Ok "Ollama מותקן"
} elseif (Test-Command "winget") {
    Write-Host "      מתקין Ollama דרך winget..."
    winget install --id Ollama.Ollama --accept-source-agreements --accept-package-agreements
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                [Environment]::GetEnvironmentVariable("Path", "User")
    if (Test-Command "ollama") { Write-Ok "Ollama הותקן" }
    else {
        Write-Warn2 "Ollama הותקן אך אינו ב-PATH. פתח חלון PowerShell חדש והרץ שוב."
        exit 1
    }
} else {
    Write-Fail "Ollama חסר ואין winget."
    Write-Host "      הורד מ: https://ollama.com/download/windows" -ForegroundColor Yellow
    exit 1
}

# ---------------------------------------------------------------------------
Write-Step 5 "שרת Ollama + מודל"
# ---------------------------------------------------------------------------
$serverUp = $false
try {
    Invoke-WebRequest -Uri "http://localhost:11434/api/tags" -TimeoutSec 3 -UseBasicParsing | Out-Null
    $serverUp = $true
} catch { $serverUp = $false }

if ($serverUp) {
    Write-Ok "שרת Ollama רץ"
} else {
    Write-Host "      מפעיל את שרת Ollama ברקע..."
    Start-Process -FilePath "ollama" -ArgumentList "serve" -WindowStyle Hidden
    for ($i = 0; $i -lt 15; $i++) {
        Start-Sleep -Seconds 1
        try {
            Invoke-WebRequest -Uri "http://localhost:11434/api/tags" -TimeoutSec 2 -UseBasicParsing | Out-Null
            $serverUp = $true; break
        } catch { }
    }
    if ($serverUp) { Write-Ok "שרת Ollama עלה" }
    else { Write-Warn2 "השרת לא ענה. הרץ 'ollama serve' בחלון נפרד." }
}

if ($SkipModel) {
    Write-Warn2 "דילוג על הורדת המודל (--SkipModel)"
} elseif ($serverUp) {
    $installed = (ollama list 2>$null | Out-String)
    if ($installed -match [regex]::Escape($RequiredModel)) {
        Write-Ok "$RequiredModel כבר מותקן"
    } else {
        Write-Host "      מוריד את $RequiredModel (~3.3GB, פעם אחת)..."
        ollama pull $RequiredModel
        if ($LASTEXITCODE -eq 0) { Write-Ok "$RequiredModel הורד" }
        else { Write-Warn2 "ההורדה נכשלה. הרץ ידנית: ollama pull $RequiredModel" }
    }
}
# qwen2.5-coder:7b ו-qwen3:8b נחוצים רק ל-/build ול-/reason. הם כבדים,
# ולכן אינם מותקנים אוטומטית - ראה README.

# ---------------------------------------------------------------------------
Write-Step 6 "בדיקת תקינות"
# ---------------------------------------------------------------------------
& $VenvPython (Join-Path $Root "scripts\check.py")
if ($LASTEXITCODE -ne 0) {
    Write-Fail "הבדיקה נכשלה. אל תמשיך לפני שהיא ירוקה."
    exit 1
}

# ---------------------------------------------------------------------------
Write-Step 7 "הרצה"
# ---------------------------------------------------------------------------
if ($NoLaunch) {
    Write-Ok "ההתקנה הושלמה. להרצה:  .\scripts\run.ps1"
    exit 0
}

Write-Host "`n   פותח את האפליקציה על http://localhost:8501" -ForegroundColor White
Write-Host "   לעצירה: Ctrl+C`n" -ForegroundColor DarkGray
& (Join-Path $PSScriptRoot "run.ps1")
