<#
.SYNOPSIS
    Starts the local Qwen3-Embedding llama-server for Mondo Music Video.
.DESCRIPTION
    Launches Qwen3-Embedding-0.6B on CPU (port 8092) with last-token pooling
    for vocabulary clustering, deduplication, and style vector sidecars.
.EXAMPLE
    .\start-embedding.ps1
    .\start-embedding.ps1 -Port 8092
#>
param(
    [int]$Port = 8092,
    [string]$LlamaDir = "C:\llamaCPP",
    [string]$ModelPath = $env:MMV_EMBEDDING_MODEL,
    [string]$ServerExe = "",
    [int]$SleepIdleSeconds = 10,
    [switch]$Foreground
)

$ErrorActionPreference = "Stop"

# Fall back to the app's own settings.json: the writer launch command names the llama-server in use.
if (-not $PSBoundParameters.ContainsKey("ServerExe") -and -not (Test-Path (Join-Path $LlamaDir "llama-server*"))) {
    $settingsFile = @($(if ($env:MMV_HOME) { Join-Path $env:MMV_HOME "settings.json" }),
        $(if ($env:LOCALAPPDATA) { Join-Path $env:LOCALAPPDATA "mondo-music-video\settings.json" }),
        (Join-Path $PSScriptRoot "data\settings.json")) |
        Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
    if ($settingsFile) {
        try {
            $launch = (Get-Content $settingsFile -Raw -Encoding UTF8 | ConvertFrom-Json).writer_launch | ConvertFrom-Json
            if ($launch -and (Test-Path $launch[0])) {
                $ServerExe = $launch[0]
                $LlamaDir = Split-Path (Split-Path $ServerExe)
                if (-not (Test-Path (Join-Path $LlamaDir "models"))) { $LlamaDir = Split-Path $ServerExe }
            }
        } catch { Write-Host "[!] Could not read llama-server from $settingsFile; using defaults." -ForegroundColor Yellow }
    }
}

# llama-server: explicit -ServerExe, then LlamaDir, then PATH (Windows .exe or other platforms).
$serverExe = $ServerExe
if (-not $serverExe) {
    $inDir = @("llama-server.exe", "llama-server") | ForEach-Object { Join-Path $LlamaDir $_ } | Where-Object { Test-Path $_ } | Select-Object -First 1
    $serverExe = if ($inDir) { $inDir } else { (Get-Command llama-server -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty Source) }
}
if (-not $serverExe -or -not (Test-Path $serverExe)) {
    Write-Error "Could not find llama-server in $LlamaDir or on PATH. Pass -ServerExe <path> or -LlamaDir <folder>."
    exit 1
}

# Model: explicit -ModelPath / MMV_EMBEDDING_MODEL, then the usual names, then a non-recursive look in LlamaDir\models.
$modelDir = Join-Path $LlamaDir "models\Qwen"
$modelPath = @($ModelPath,
    (Join-Path $modelDir "Qwen3-Embedding-0.6B-Q8_0.gguf"),
    (Join-Path $modelDir "Qwen3-Embedding-0.6B-f16.gguf")) |
    Where-Object { $_ -and (Test-Path $_ -PathType Leaf) } | Select-Object -First 1
if (-not $modelPath) {
    # One level only, no recursion: LlamaDir\models and LlamaDir\models\<subfolder>.
    $modelPath = @((Join-Path $LlamaDir "models\*Qwen3-Embedding*.gguf"), (Join-Path $LlamaDir "models\*\*Qwen3-Embedding*.gguf")) |
        ForEach-Object { Get-ChildItem -Path $_ -File -ErrorAction SilentlyContinue } |
        Select-Object -First 1 -ExpandProperty FullName
}
if (-not $modelPath) {
    Write-Error "Could not find a Qwen3-Embedding GGUF. Pass -ModelPath <file> or set MMV_EMBEDDING_MODEL; see docs/QWEN_EMBEDDING_SETUP.md. Nothing is downloaded by this script."
    exit 1
}

$testUrl = "http://127.0.0.1:$Port/health"
function Test-HttpOk([string]$url, [int]$timeoutSec = 2) {
    try {
        $req = [System.Net.WebRequest]::Create($url)
        $req.Timeout = $timeoutSec * 1000
        $req.Method = "GET"
        $resp = $req.GetResponse()
        $resp.Close()
        return $true
    } catch {
        return $false
    }
}

if (Test-HttpOk $testUrl 1) {
    Write-Host "[+] Qwen3-Embedding server is already running on http://127.0.0.1:$Port" -ForegroundColor Green
    exit 0
}

Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "  Starting Qwen3-Embedding Server (Port $Port)" -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "Model:   $modelPath" -ForegroundColor White
Write-Host "Device:  CPU (-ngl 0)" -ForegroundColor Gray
Write-Host "Pooling: last" -ForegroundColor Gray
Write-Host "Sleep:   $SleepIdleSeconds s (frees RAM when idle)" -ForegroundColor Gray

$serverArgs = @(
    "-m", "$modelPath",
    "--embeddings",
    "--pooling", "last",
    "--port", "$Port",
    "--host", "127.0.0.1",
    "-ngl", "0",
    "--alias", "qwen3-embedding",
    "--sleep-idle-seconds", "$SleepIdleSeconds",
    "--parallel", "2"
)

if ($Foreground) {
    & $serverExe @serverArgs
} else {
    Start-Process -FilePath $serverExe -ArgumentList $serverArgs -WorkingDirectory (Split-Path $serverExe) -WindowStyle Minimized
    Write-Host "[-] Waiting for embedding server to initialize..." -NoNewline
    $ready = $false
    for ($i = 0; $i -lt 15; $i++) {
        Start-Sleep -Seconds 1
        Write-Host "." -NoNewline
        if (Test-HttpOk $testUrl 1) {
            $ready = $true
            break
        }
    }
    Write-Host ""
    if ($ready) {
        Write-Host "[+] Qwen3-Embedding server is ready on http://127.0.0.1:$Port" -ForegroundColor Green
        Write-Host "    Endpoint: http://127.0.0.1:$Port/v1/embeddings" -ForegroundColor DarkGray
    } else {
        Write-Warning "Server process started, but health check timed out. Check the minimized console window for errors."
    }
}

