# Spec Check — end-to-end setup (Windows PowerShell)
# Usage:
#   .\setup.ps1                          Local setup (repo folder)
#   .\setup.ps1 -Server                  Server setup (192.168.10.38:7004)
#   .\setup.ps1 -AdminPassword "MySecurePass123"
#   .\setup.ps1 -Server -AdminPassword "MySecurePass123"
#   .\setup.ps1 -SkipFrontend

param(
    [string]$AdminPassword = "",
    [switch]$SkipFrontend,
    [switch]$Server
)

# Server deployment constants (LAN host at 192.168.10.38, app on port 7004)
$ServerRoot = "C:\AI_Code\Spec_Check_RAG_V1_7004\Spec-Check-RAG"
$ServerHost = "192.168.10.38"
$ServerFrontendPort = "7004"
$ServerBackendPort = "7005"

$ErrorActionPreference = "Stop"
if ($Server) {
    $Root = $ServerRoot
} else {
    $Root = $PSScriptRoot
}
$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"
$VenvPython = Join-Path $Backend "venv\Scripts\python.exe"
$VenvPip = Join-Path $Backend "venv\Scripts\pip.exe"

function Write-Step([string]$Message) {
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Test-Command([string]$Name) {
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Get-VersionNumber([string]$Text) {
    if ($Text -match "(\d+)\.(\d+)") {
        return [int]$Matches[1] * 100 + [int]$Matches[2]
    }
    return 0
}

function Update-DotEnvValue {
    param(
        [string]$Path,
        [string]$Key,
        [string]$Value
    )
    if (-not (Test-Path $Path)) {
        return
    }
    $lines = Get-Content $Path
    $found = $false
    $newLines = foreach ($line in $lines) {
        if ($line -match "^$([regex]::Escape($Key))=") {
            $found = $true
            "$Key=$Value"
        } else {
            $line
        }
    }
    if (-not $found) {
        $newLines += "$Key=$Value"
    }
    $newLines | Set-Content -Path $Path -Encoding utf8
}

Write-Host ""
if ($Server) {
    Write-Host " Spec Check — SERVER setup" -ForegroundColor Green
    Write-Host " Target:     http://${ServerHost}:${ServerFrontendPort}"
    Write-Host " API:        http://${ServerHost}:${ServerBackendPort}/api/v1"
} else {
    Write-Host " Spec Check — LOCAL setup" -ForegroundColor Green
}
Write-Host " Repository: $Root"
Write-Host ""

if ($Server -and -not (Test-Path $Root)) {
    Write-Host "ERROR: Server project path not found:" -ForegroundColor Red
    Write-Host "  $Root"
    Write-Host ""
    Write-Host "Copy the project to that path on the server, then re-run:"
    Write-Host "  setup.bat server"
    exit 1
}

# ── Prerequisites ────────────────────────────────────────────────────────────
Write-Step "Checking prerequisites"

if (-not (Test-Command "python")) {
    Write-Host "ERROR: Python not found. Install Python 3.11+ and add it to PATH." -ForegroundColor Red
    exit 1
}

$pyVersion = (& python --version 2>&1) -join " "
$pyNum = Get-VersionNumber $pyVersion
if ($pyNum -lt 311) {
    Write-Host "ERROR: Python 3.11+ required (found: $pyVersion)." -ForegroundColor Red
    exit 1
}
Write-Host "OK  Python: $pyVersion"

if (-not $SkipFrontend) {
    if (-not (Test-Command "node")) {
        Write-Host "ERROR: Node.js not found. Install Node.js 18+." -ForegroundColor Red
        exit 1
    }
    $nodeVersion = (& node --version 2>&1) -join " "
    $nodeNum = Get-VersionNumber $nodeVersion
    if ($nodeNum -lt 1800) {
        Write-Host "ERROR: Node.js 18+ required (found: $nodeVersion)." -ForegroundColor Red
        exit 1
    }
    Write-Host "OK  Node: $nodeVersion"

    if (-not (Test-Command "npm")) {
        Write-Host "ERROR: npm not found." -ForegroundColor Red
        exit 1
    }
    Write-Host "OK  npm: $(npm --version)"
}

if (Test-Command "psql") {
    Write-Host "OK  psql found (optional — used for DB hints)"
} else {
    Write-Host "NOTE  psql not on PATH — database must exist or setup_project.py will try CREATE DATABASE"
}

if (Test-Command "tesseract") {
    Write-Host "OK  Tesseract OCR found"
} else {
    Write-Host "NOTE  Tesseract not on PATH — scanned PDF OCR may fail (set PARSING_OCR_ENABLED=False for text PDFs)"
}

# ── Backend virtualenv ────────────────────────────────────────────────────────
Write-Step "Backend Python environment"

if (-not (Test-Path $VenvPython)) {
    Write-Host "Creating virtualenv..."
    Push-Location $Backend
    python -m venv venv
    Pop-Location
} else {
    Write-Host "Virtualenv already exists."
}

Write-Host "Installing Python dependencies (this may take a few minutes)..."
& $VenvPip install --upgrade pip | Out-Null
& $VenvPip install -r (Join-Path $Backend "requirements.txt")
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: pip install failed." -ForegroundColor Red
    exit 1
}
Write-Host "OK  requirements installed"

# ── Backend .env ─────────────────────────────────────────────────────────────
Write-Step "Backend environment file"

$EnvExample = Join-Path $Backend ".env.example"
$EnvFile = Join-Path $Backend ".env"

if (-not (Test-Path $EnvFile)) {
    if (-not (Test-Path $EnvExample)) {
        Write-Host "ERROR: backend/.env.example not found." -ForegroundColor Red
        exit 1
    }
    Copy-Item $EnvExample $EnvFile
    Write-Host "Created backend/.env from .env.example"
    Write-Host ""
    Write-Host "IMPORTANT: Edit backend/.env before processing documents:" -ForegroundColor Yellow
    Write-Host "  - DATABASE_URL (PostgreSQL connection)"
    Write-Host "  - OPENAI_API_KEY or Azure OpenAI settings (AI_PROVIDER=azure)"
    Write-Host ""
} else {
    Write-Host "backend/.env already exists (not overwritten)."
}

# Quick sanity check for placeholder values
$envContent = Get-Content $EnvFile -Raw
if ($envContent -match "your_password|sk-your-key-here") {
    Write-Host "WARNING: backend/.env still has placeholder credentials." -ForegroundColor Yellow
}

if ($Server) {
    Write-Step "Server network settings (backend/.env)"
    $allowedHosts = "localhost,127.0.0.1,$ServerHost"
    $corsOrigins = "http://localhost:$ServerFrontendPort,http://127.0.0.1:$ServerFrontendPort,http://${ServerHost}:$ServerFrontendPort"
    Update-DotEnvValue -Path $EnvFile -Key "ALLOWED_HOSTS" -Value $allowedHosts
    Update-DotEnvValue -Path $EnvFile -Key "CORS_ALLOWED_ORIGINS" -Value $corsOrigins
    Write-Host "OK  ALLOWED_HOSTS=$allowedHosts"
    Write-Host "OK  CORS_ALLOWED_ORIGINS=$corsOrigins"
}

# ── Database + migrations + admin ───────────────────────────────────────────
Write-Step "Database, migrations, admin user"

$setupArgs = @((Join-Path $Root "scripts\setup_project.py"))
if ($AdminPassword) {
    $setupArgs += "--admin-password=$AdminPassword"
}

& $VenvPython @setupArgs
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "Setup stopped at database/migration step." -ForegroundColor Red
    Write-Host "Fix backend/.env (DATABASE_URL) and ensure PostgreSQL is running, then re-run setup.ps1"
    exit 1
}

# ── Frontend ───────────────────────────────────────────────────────────────
if (-not $SkipFrontend) {
    Write-Step "Frontend dependencies"

    Push-Location $Frontend
    if (-not (Test-Path "node_modules")) {
        npm install
    } else {
        Write-Host "node_modules exists — running npm install to sync..."
        npm install
    }
    if ($LASTEXITCODE -ne 0) {
        Pop-Location
        Write-Host "ERROR: npm install failed." -ForegroundColor Red
        exit 1
    }
    Pop-Location
    Write-Host "OK  frontend dependencies installed"

    Write-Step "Frontend environment file"
    $feEnv = Join-Path $Frontend ".env.local"
    if ($Server) {
        $backendPort = $ServerBackendPort
        $publicHost = $ServerHost
    } else {
        $backendPort = "8004"
        $publicHost = "localhost"
    }
    @"
NEXT_PUBLIC_API_BASE_URL=http://${publicHost}:$backendPort/api/v1
NEXT_PUBLIC_API_HEALTH_URL=http://${publicHost}:$backendPort/api/health/
"@ | Set-Content -Path $feEnv -Encoding utf8
    Write-Host "Wrote frontend/.env.local (API -> http://${publicHost}:$backendPort)"
}

# ── Done ─────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host " Setup complete!" -ForegroundColor Green
Write-Host ""
Write-Host " Next steps:"
Write-Host "   1. Confirm backend/.env has valid DATABASE_URL and AI keys"
if ($Server) {
    Write-Host "   2. Start the app:  start.bat server"
    Write-Host "   3. Open:           http://${ServerHost}:${ServerFrontendPort}"
} else {
    Write-Host "   2. Start the app:  .\start.bat"
    Write-Host "   3. Open:           http://localhost:3010"
}
Write-Host "   4. Login:          admin@itcube.net (password printed above if newly created)"
Write-Host ""
Write-Host " Optional:"
Write-Host "   - Redis: not required when PROCESSING_SYNC=True and INTELLIGENCE_SYNC_GENERATION=True"
Write-Host "   - DOCX preview: install LibreOffice or set DOCX_PREVIEW_USE_WORD=True"
if ($Server) {
    Write-Host ""
    Write-Host " Server ports:"
    Write-Host "   - Frontend (LAN):  http://${ServerHost}:${ServerFrontendPort}"
    Write-Host "   - Backend API:     http://${ServerHost}:${ServerBackendPort}/api/v1"
    Write-Host "   - Project path:    $ServerRoot"
}
Write-Host ""
