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
    [int]$SleepIdleSeconds = 10,
    [switch]$Foreground
)

$ErrorActionPreference = "Stop"

$serverExe = Join-Path $LlamaDir "llama-server.exe"
if (-not (Test-Path $serverExe)) {
    Write-Error "Could not find llama-server.exe at $serverExe"
    exit 1
}

$modelDir = Join-Path $LlamaDir "models\Qwen"
$preferredModel = Join-Path $modelDir "Qwen3-Embedding-0.6B-Q8_0.gguf"
$fallbackModel = Join-Path $modelDir "Qwen3-Embedding-0.6B-f16.gguf"

if (Test-Path $preferredModel) {
    $modelPath = $preferredModel
} elseif (Test-Path $fallbackModel) {
    $modelPath = $fallbackModel
} else {
    $found = Get-ChildItem -Path (Join-Path $LlamaDir "models") -Recurse -Filter "*Qwen3-Embedding*.gguf" -File -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($found) {
        $modelPath = $found.FullName
    } else {
        Write-Error "Could not find Qwen3-Embedding GGUF in $LlamaDir\models. See docs/QWEN_EMBEDDING_SETUP.md for download instructions."
        exit 1
    }
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
    Start-Process -FilePath $serverExe -ArgumentList $serverArgs -WorkingDirectory $LlamaDir -WindowStyle Minimized
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

