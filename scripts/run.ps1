<#
.SYNOPSIS
    מריץ את יערים (אחרי install.ps1).

.DESCRIPTION
    ברירת מחדל: ממשק הווב.  -Cli מריץ את ה-CLI של הבנייה העצמית (/build).

.EXAMPLE
    .\scripts\run.ps1
    .\scripts\run.ps1 -Cli
#>

[CmdletBinding()]
param([switch]$Cli)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
    Write-Host "לא נמצאה סביבה וירטואלית. הרץ קודם:" -ForegroundColor Red
    Write-Host "  powershell -ExecutionPolicy Bypass -File scripts\install.ps1" -ForegroundColor Yellow
    exit 1
}

# החבילה יושבת תחת src/ (src-layout). בלי זה "import yoni" נכשל.
$env:PYTHONPATH = Join-Path $Root "src"

# Ollama רץ על המכונה עצמה - לא בקונטיינר, ולכן localhost.
if (-not $env:OLLAMA_HOST) { $env:OLLAMA_HOST = "http://localhost:11434" }

try {
    Invoke-WebRequest -Uri "$env:OLLAMA_HOST/api/tags" -TimeoutSec 3 -UseBasicParsing | Out-Null
} catch {
    Write-Host "שרת Ollama אינו עונה על $env:OLLAMA_HOST." -ForegroundColor Yellow
    Write-Host "המסכים ייטענו, אבל שיחה עם יוני תיכשל. הפעל בחלון נפרד:  ollama serve`n" -ForegroundColor Yellow
}

Push-Location $Root
try {
    if ($Cli) {
        & $VenvPython -m yoni
    } else {
        & $VenvPython -m streamlit run "src\yoni\interfaces\web\app.py" `
            --server.port=8501 --browser.gatherUsageStats=false
    }
} finally {
    Pop-Location
}
