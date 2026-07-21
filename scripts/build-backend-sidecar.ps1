param(
    [string]$PythonExecutable = "python"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$BackendDir = Join-Path $Root "backend"
$EntryPoint = Join-Path $BackendDir "main.py"
$LockFile = Join-Path $BackendDir "requirements-windows.lock"
$VenvDir = Join-Path $Root ".venv-windows-build"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$BuildDir = Join-Path $BackendDir "build\windows"
$DistDir = Join-Path $BackendDir "dist"
$TargetName = "mutinychat-backend-x86_64-pc-windows-msvc"
$TargetExe = Join-Path $DistDir "$TargetName.exe"

function Assert-LastExitCode([string]$Activity) {
    if ($LASTEXITCODE -ne 0) {
        throw "$Activity failed with exit code $LASTEXITCODE"
    }
}

if (-not (Test-Path -LiteralPath $EntryPoint -PathType Leaf)) {
    throw "Backend entry point not found: $EntryPoint"
}
if (-not (Test-Path -LiteralPath $LockFile -PathType Leaf)) {
    throw "Pinned Windows requirements not found: $LockFile"
}

Write-Host "[INFO] Verifying Python: $PythonExecutable"
& $PythonExecutable --version
Assert-LastExitCode "Python detection"

if (-not (Test-Path -LiteralPath $VenvPython -PathType Leaf)) {
    Write-Host "[INFO] Creating isolated Windows build environment..."
    & $PythonExecutable -m venv $VenvDir
    Assert-LastExitCode "Virtual environment creation"
}

Write-Host "[INFO] Installing pinned backend build dependencies..."
& $VenvPython -m pip install --disable-pip-version-check --no-input -r $LockFile
Assert-LastExitCode "Pinned dependency installation"

if (Test-Path -LiteralPath $BuildDir) {
    Remove-Item -LiteralPath $BuildDir -Recurse -Force
}
New-Item -ItemType Directory -Path $BuildDir -Force | Out-Null
New-Item -ItemType Directory -Path $DistDir -Force | Out-Null
if (Test-Path -LiteralPath $TargetExe) {
    Remove-Item -LiteralPath $TargetExe -Force
}

Write-Host "[INFO] Building self-contained backend sidecar..."
$PyInstallerArgs = @(
    "-m", "PyInstaller",
    "--clean",
    "--noconfirm",
    "--onefile",
    "--console",
    "--name", $TargetName,
    "--distpath", $DistDir,
    "--workpath", $BuildDir,
    "--specpath", $BuildDir,
    "--collect-all", "nacl",
    "--exclude-module", "cryptography",
    "--hidden-import", "_cffi_backend",
    "--hidden-import", "socks",
    $EntryPoint
)
& $VenvPython @PyInstallerArgs
Assert-LastExitCode "PyInstaller backend build"

if (-not (Test-Path -LiteralPath $TargetExe -PathType Leaf)) {
    throw "PyInstaller reported success but the sidecar was not created: $TargetExe"
}

Write-Host "[INFO] Running backend command-line smoke test..."
$PingOutput = (& $TargetExe --command ping | Out-String).Trim()
Assert-LastExitCode "Backend command-line ping"
$PingJson = $PingOutput | ConvertFrom-Json
if ($PingJson.status -ne "MutinyChat backend alive") {
    throw "Unexpected backend ping response: $PingOutput"
}

Write-Host "[INFO] Running backend stdio JSON smoke test..."
$StartInfo = [System.Diagnostics.ProcessStartInfo]::new()
$StartInfo.FileName = $TargetExe
$StartInfo.Arguments = "--stdio-json"
$StartInfo.UseShellExecute = $false
$StartInfo.RedirectStandardInput = $true
$StartInfo.RedirectStandardOutput = $true
$StartInfo.RedirectStandardError = $true
$StartInfo.CreateNoWindow = $true
$Process = [System.Diagnostics.Process]::new()
$Process.StartInfo = $StartInfo
if (-not $Process.Start()) {
    throw "Failed to start backend stdio smoke process"
}
try {
    $Process.StandardInput.WriteLine('{"cmd":"ping"}')
    $Process.StandardInput.Flush()
    $ResponseLine = $Process.StandardOutput.ReadLine()
    $Process.StandardInput.Close()
    if (-not $Process.WaitForExit(15000)) {
        $Process.Kill($true)
        throw "Backend stdio smoke process did not exit"
    }
    if ($Process.ExitCode -ne 0) {
        $ErrorText = $Process.StandardError.ReadToEnd()
        throw "Backend stdio smoke process failed: $ErrorText"
    }
    $Response = $ResponseLine | ConvertFrom-Json
    if ($Response.status -ne "MutinyChat backend alive") {
        throw "Unexpected backend stdio response: $ResponseLine"
    }
}
finally {
    $Process.Dispose()
}

$Hash = (Get-FileHash -LiteralPath $TargetExe -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Host "[OK] Built $TargetExe"
Write-Host "[OK] SHA-256: $Hash"
