<#
.SYNOPSIS
    Mondo Music Video Launcher & llama.cpp Model Selector
.DESCRIPTION
    Launches Mondo Music Video and connects to or starts your local llama-server
    with interactive model selection from C:\llamaCPP\models.
.EXAMPLE
    .\start.ps1
    .\start.ps1 -SelectModel
    .\start.ps1 -Gui
    .\start.ps1 -Model "Qwen3-VL-8B"
#>
param(
    [switch]$SelectModel,
    [switch]$Gui,
    [string]$Model = "",
    [int]$Port = 8091,
    [int]$LlamaPort = 8081,
    [ValidateRange(512, 1048576)]
    [int]$ContextSize = 8192,
    [string]$TuningPreset = "current",
    [ValidateRange(0, 1048576)]
    [int]$BatchSize = 0,
    [ValidateRange(0, 1048576)]
    [int]$MicroBatchSize = 0,
    [ValidateRange(0, 1048576)]
    [int]$ImageMinTokens = 0,
    [string]$LlamaDir = "C:\llamaCPP",
    [switch]$NoLlama,
    [switch]$NoBrowser,
    [switch]$Help
)

$ErrorActionPreference = "Stop"

if ($Help) {
    Write-Host ""
    Write-Host "Mondo Music Video Launcher" -ForegroundColor Cyan
    Write-Host "--------------------------" -ForegroundColor DarkCyan
    Write-Host "Usage: .\start.ps1 [options]"
    Write-Host ""
    Write-Host "Options:"
    Write-Host "  -SelectModel       Interactively choose a GGUF model from llama.cpp"
    Write-Host "  -Gui               Open the llama.cpp graphical launcher (launcher.ps1)"
    Write-Host "  -Model <name>      Select model matching name or substring"
    Write-Host "  -Port <int>        Mondo Studio web port (default: 8091)"
    Write-Host "  -LlamaPort <int>   llama-server port (default: 8081)"
    Write-Host "  -TuningPreset <name> current (default) or context_16k (16k/vision batches)"
    Write-Host "  -ContextSize <int> llama-server context window (default: 8192)"
    Write-Host "  -BatchSize <int>   Optional logical batch size; 0 keeps server default"
    Write-Host "  -MicroBatchSize <int> Optional micro-batch size; 0 keeps server default"
    Write-Host "  -ImageMinTokens <int> Optional vision token minimum; 0 keeps server default"
    Write-Host "  -LlamaDir <path>   llama.cpp installation directory (default: C:\llamaCPP)"
    Write-Host "  -NoLlama           Skip llama.cpp management (assume already running)"
    Write-Host "  -NoBrowser         Do not automatically open the browser"
    Write-Host ""
    exit 0
}

if ($TuningPreset -notin @("current", "context_16k", "hellonearthis")) {
    throw "Choose current or context_16k for -TuningPreset."
}
$UseAlternateTuning = $TuningPreset -in @("context_16k", "hellonearthis")
if ($UseAlternateTuning) {
    if (-not $PSBoundParameters.ContainsKey("ContextSize")) { $ContextSize = 16384 }
    if (-not $PSBoundParameters.ContainsKey("BatchSize")) { $BatchSize = 2048 }
    if (-not $PSBoundParameters.ContainsKey("MicroBatchSize")) { $MicroBatchSize = 1024 }
    if (-not $PSBoundParameters.ContainsKey("ImageMinTokens")) { $ImageMinTokens = 1024 }
} else {
    if (-not $PSBoundParameters.ContainsKey("ContextSize")) {
        try {
            $settingsFile = Join-Path $env:LOCALAPPDATA "mondo-music-video\settings.json"
            if (Test-Path $settingsFile) {
                $existing = Get-Content $settingsFile -Raw -Encoding UTF8 | ConvertFrom-Json
                if ($existing.writer_launch) {
                    $existingLaunch = $existing.writer_launch | ConvertFrom-Json
                    for ($k = 0; $k -lt $existingLaunch.Length - 1; $k++) {
                        if ($existingLaunch[$k] -in @("-c", "--ctx-size")) {
                            $parsedCtx = [int]$existingLaunch[$k + 1]
                            if ($parsedCtx -ge 512) { $ContextSize = $parsedCtx }
                        } elseif ($existingLaunch[$k] -in @("-b", "--batch-size") -and -not $PSBoundParameters.ContainsKey("BatchSize")) {
                            $parsedB = [int]$existingLaunch[$k + 1]
                            if ($parsedB -gt 0) { $BatchSize = $parsedB }
                        } elseif ($existingLaunch[$k] -in @("-ub", "--ubatch-size") -and -not $PSBoundParameters.ContainsKey("MicroBatchSize")) {
                            $parsedUb = [int]$existingLaunch[$k + 1]
                            if ($parsedUb -gt 0) { $MicroBatchSize = $parsedUb }
                        } elseif ($existingLaunch[$k] -eq "--image-min-tokens" -and -not $PSBoundParameters.ContainsKey("ImageMinTokens")) {
                            $parsedImg = [int]$existingLaunch[$k + 1]
                            if ($parsedImg -gt 0) { $ImageMinTokens = $parsedImg }
                        }
                    }
                }
            }
        } catch {}
    }
}

# One slot gives the whole context to the active prompt (the default 4 slots leave each a quarter, which truncates long passages
# on low-memory machines). Dropping the prompt cache is opt-in with alternate tuning: it keeps earlier passages out of VRAM but reuses less.
$SlotArgs = @("--parallel", "1") + $(if ($UseAlternateTuning) { @("--no-cache-prompt", "-sps", "0") } else { @() })

$MmvProjectDir = $PSScriptRoot
if (-not $MmvProjectDir) { $MmvProjectDir = (Get-Location).Path }
$MmvPython = Join-Path $MmvProjectDir ".venv\Scripts\python.exe"

if (-not (Test-Path $MmvPython)) {
    Write-Host "[!] Virtual environment not found. Running install.ps1..." -ForegroundColor Yellow
    & (Join-Path $MmvProjectDir "install.ps1")
    if (-not (Test-Path $MmvPython)) {
        throw "Could not find Python in .venv. Run install.ps1 first."
    }
}

$modelsDir = Join-Path $LlamaDir "models"
$serverExe = Join-Path $LlamaDir "llama-server.exe"
$launcherPs1 = Join-Path $LlamaDir "launcher.ps1"
$launcherConfig = Join-Path $LlamaDir "launcher_config.json"

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

function Get-DiscoveredModels {
    $found = @()
    if (-not (Test-Path $modelsDir)) { return $found }
    $files = Get-ChildItem -Path $modelsDir -Recurse -Filter "*.gguf" -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -notmatch "mmproj" }

    foreach ($file in $files) {
        $relPath = $file.FullName.Substring($LlamaDir.Length).TrimStart("\/")
        $dir = $file.DirectoryName
        $proj = Get-ChildItem -Path $dir -Filter "*mmproj*.gguf" -File -ErrorAction SilentlyContinue | Select-Object -First 1
        $projRel = if ($proj) { $proj.FullName.Substring($LlamaDir.Length).TrimStart("\/") } else { "" }
        $sizeGb = [Math]::Round($file.Length / 1GB, 2)
        $parentFolder = $file.Directory.Parent.Name
        if ($file.Directory.FullName -eq $modelsDir) {
            $folderTag = "(Root)"
        } elseif ($parentFolder -and $parentFolder -ne "models") {
            $folderTag = "$parentFolder/" + $file.Directory.Name
        } else {
            $folderTag = $file.Directory.Name
        }
        $name = [System.IO.Path]::GetFileNameWithoutExtension($file.Name)
        $alias = $name.ToLower() -replace "-gguf$", "" -replace "-q[0-9].*$", "" -replace "-bf16.*$", "" -replace "-f16.*$", ""

        $found += [PSCustomObject]@{
            Name          = $name
            FileName      = $file.Name
            RelativePath  = $relPath
            FullPath      = $file.FullName
            SizeGB        = $sizeGb
            HasVision     = ($projRel -ne "")
            MmprojRelPath = $projRel
            FolderTag     = $folderTag
            DefaultAlias  = $alias
        }
    }
    return $found
}

# If GUI requested
if ($Gui -and (Test-Path $launcherPs1)) {
    Write-Host "[*] Launching llama.cpp GUI launcher ($launcherPs1)..." -ForegroundColor Cyan
    Start-Process powershell -ArgumentList "-ExecutionPolicy Bypass -File `"$launcherPs1`""
}

# Model selection logic
$selectedModel = $null
$models = Get-DiscoveredModels

if ($Model) {
    $match = $models | Where-Object { $_.Name -like "*$Model*" -or $_.RelativePath -like "*$Model*" } | Select-Object -First 1
    if ($match) {
        $selectedModel = $match
        Write-Host "[+] Selected model by query: $($selectedModel.Name)" -ForegroundColor Green
    } else {
        Write-Warning "Model matching '$Model' not found in $modelsDir. Falling back to selector."
    }
}

if (-not $selectedModel -and ($SelectModel -or $models.Count -gt 0)) {
    # Check if last model from launcher_config.json is available
    $defaultIndex = 1
    $lastModelPath = ""
    if (Test-Path $launcherConfig) {
        try {
            $cfg = Get-Content $launcherConfig -Raw | ConvertFrom-Json
            $lastModelPath = $cfg.LastModel
        } catch {}
    }

    if ($lastModelPath) {
        for ($i = 0; $i -lt $models.Count; $i++) {
            if ($models[$i].RelativePath -eq $lastModelPath) {
                $defaultIndex = $i + 1
                break
            }
        }
    }

    if ($SelectModel) {
        Write-Host ""
        Write-Host "======================================================================" -ForegroundColor Cyan
        Write-Host "  Mondo Music Video - llama.cpp Model Selector" -ForegroundColor Cyan
        Write-Host "======================================================================" -ForegroundColor Cyan
        Write-Host ""

        for ($i = 0; $i -lt $models.Count; $i++) {
            $m = $models[$i]
            $vis = if ($m.HasVision) { "[Vision]" } else { "        " }
            $isDef = if (($i + 1) -eq $defaultIndex) { "*" } else { " " }
            $num = ("{0}[{1,2}]" -f $isDef, ($i + 1))
            Write-Host " $num " -NoNewline -ForegroundColor Yellow
            Write-Host "$($vis) " -NoNewline -ForegroundColor Green
            Write-Host ("{0,-40}" -f $m.Name) -NoNewline -ForegroundColor White
            Write-Host (" {0,5} GB" -f $m.SizeGB) -NoNewline -ForegroundColor Gray
            Write-Host "  ($($m.FolderTag))" -ForegroundColor DarkGray
        }

        Write-Host ""
        $choice = Read-Host "Select model number [1-$($models.Count), default $defaultIndex]"
        $idx = $defaultIndex
        if ([int]::TryParse($choice, [ref]$idx) -and $idx -ge 1 -and $idx -le $models.Count) {
            $selectedModel = $models[$idx - 1]
        } else {
            $selectedModel = $models[$defaultIndex - 1]
        }
    } else {
        $selectedModel = $models[$defaultIndex - 1]
    }
}

# Update Mondo Studio settings with selected model
if ($selectedModel) {
    Write-Host "[+] Configuring Mondo Music Video for model: $($selectedModel.Name)" -ForegroundColor Cyan
    $launchArgs = @(
        "$serverExe",
        "-m", "$($selectedModel.RelativePath)",
        "-ngl", "99",
        "-c", "$ContextSize",
        "--flash-attn", "on",
        "--host", "127.0.0.1",
        "--port", "$LlamaPort",
        "--alias", "$($selectedModel.DefaultAlias)",
        "--sleep-idle-seconds", "10"
    )
    $launchArgs += $SlotArgs
    if ($selectedModel.HasVision -and $selectedModel.MmprojRelPath) {
        $launchArgs += @("--mmproj", "$($selectedModel.MmprojRelPath)")
    }
    if ($BatchSize -gt 0) { $launchArgs += @("-b", "$BatchSize") }
    if ($MicroBatchSize -gt 0) { $launchArgs += @("-ub", "$MicroBatchSize") }
    if ($selectedModel.HasVision) { $launchArgs += @("--image-min-tokens", $(if ($ImageMinTokens -gt 0) { "$ImageMinTokens" } else { "1024" })) }

    $settingsPayload = @{
        writer_url = "http://127.0.0.1:$LlamaPort/v1"
        writer_model = $selectedModel.DefaultAlias
        writer_mode = "local"
        writer_launch = (ConvertTo-Json -InputObject @($launchArgs) -Compress)
        writer_cwd = $LlamaDir
    }
    if ($selectedModel.HasVision) {
        $settingsPayload.vision_url = "http://127.0.0.1:$LlamaPort/v1"
        $settingsPayload.vision_model = $selectedModel.DefaultAlias
        $settingsPayload.vision_call_estimate = 0.0
    }
    $pyCode = @"
import json, sys
from mmv.storage import Storage, write_json
store = Storage()
s = store.settings()
s.update(json.load(sys.stdin))
write_json(store.home / 'settings.json', s)
"@
    $previousOutputEncoding = $OutputEncoding
    try {
        $OutputEncoding = [System.Text.UTF8Encoding]::new($false)
        $settingsPayload | ConvertTo-Json -Compress | & $MmvPython -X utf8 -c $pyCode
    } finally {
        $OutputEncoding = $previousOutputEncoding
    }
    if ($LASTEXITCODE -ne 0) { throw "Could not save selected model settings" }
}

# Check/Launch llama-server
if (-not $NoLlama -and (Test-Path $serverExe)) {
    $llamaUrl = "http://127.0.0.1:$LlamaPort/v1/models"
    $isLlamaRunning = Test-HttpOk $llamaUrl

    if (-not $isLlamaRunning -and $selectedModel) {
        Write-Host "[*] Starting llama-server on port $LlamaPort with $($selectedModel.Name)..." -ForegroundColor Yellow
        $serverArgs = @(
            "-m", (Join-Path $LlamaDir $selectedModel.RelativePath),
            "-ngl", "99",
            "-c", "$ContextSize",
            "--flash-attn", "on",
            "--host", "127.0.0.1",
            "--port", "$LlamaPort",
            "--alias", "$($selectedModel.DefaultAlias)",
            "--sleep-idle-seconds", "10"
        )
        $serverArgs += $SlotArgs
        if ($selectedModel.HasVision -and $selectedModel.MmprojRelPath) {
            $serverArgs += @("--mmproj", (Join-Path $LlamaDir $selectedModel.MmprojRelPath))
        }

        if ($BatchSize -gt 0) { $serverArgs += @("-b", "$BatchSize") }
        if ($MicroBatchSize -gt 0) { $serverArgs += @("-ub", "$MicroBatchSize") }
        if ($selectedModel.HasVision) { $serverArgs += @("--image-min-tokens", $(if ($ImageMinTokens -gt 0) { "$ImageMinTokens" } else { "1024" })) }

        Start-Process -FilePath $serverExe -ArgumentList $serverArgs -WorkingDirectory $LlamaDir -WindowStyle Minimized

        Write-Host "[-] Waiting for llama-server to be ready..." -NoNewline
        for ($w = 0; $w -lt 25; $w++) {
            Start-Sleep -Seconds 1
            Write-Host "." -NoNewline
            if (Test-HttpOk $llamaUrl) {
                $isLlamaRunning = $true
                break
            }
        }
        Write-Host ""
        if ($isLlamaRunning) {
            Write-Host "[+] llama-server is ready on http://127.0.0.1:$LlamaPort" -ForegroundColor Green
        } else {
            Write-Warning "llama-server is still loading. Mondo will automatically start or wait for it during generation."
        }
    } elseif ($isLlamaRunning) {
        Write-Host "[+] llama-server is already running on http://127.0.0.1:$LlamaPort" -ForegroundColor Green
    }
}

# Check if Mondo Music Video Studio is already running
if (Test-HttpOk "http://127.0.0.1:$Port/api/version" 1) {
    Write-Host ""
    Write-Host "[+] Mondo Music Video Studio is already running on http://127.0.0.1:$Port" -ForegroundColor Green
    if (-not $NoBrowser) {
        Write-Host "[*] Opening browser..." -ForegroundColor Cyan
        Start-Process "http://127.0.0.1:$Port/"
    }
    return
}

# Launch Mondo Music Video Studio Server
Write-Host ""
Write-Host "======================================================================" -ForegroundColor Green
Write-Host "  Starting Mondo Music Video Studio on http://127.0.0.1:$Port" -ForegroundColor Green
Write-Host "======================================================================" -ForegroundColor Green
Write-Host ""

if (-not $NoBrowser) {
    Start-Job -ScriptBlock {
        param($p)
        Start-Sleep -Seconds 2
        Start-Process "http://127.0.0.1:$p/"
    } -ArgumentList $Port | Out-Null
}

& $MmvPython -X utf8 -m mmv.setup serve --port $Port
