param(
    [string]$TargetDirectory = "src-tauri\target\release",
    [string]$OutputDirectory = "artifacts\windows"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Target = Join-Path $Root $TargetDirectory
$Output = Join-Path $Root $OutputDirectory
$PortableRoot = Join-Path $Output "MutinyChat-portable"
$ResourceRoot = Join-Path $Root "src-tauri\resources"
$PreparedTorDirectory = Join-Path $ResourceRoot "tor"
$PreparedDataDirectory = Join-Path $ResourceRoot "data"

function Require-File([string]$Path, [string]$Label) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "$Label is missing: $Path"
    }
}

function Stage-Directory([string]$Source, [string]$Destination, [string]$Label) {
    if (-not (Test-Path -LiteralPath $Source -PathType Container)) {
        throw "$Label source directory is missing: $Source"
    }
    if (Test-Path -LiteralPath $Destination) {
        Remove-Item -LiteralPath $Destination -Recurse -Force
    }
    Copy-Item -LiteralPath $Source -Destination $Destination -Recurse -Force
}

$AppExe = Join-Path $Target "mutinychat.exe"
$BackendExe = Join-Path $Target "mutinychat-backend.exe"
$PreparedTorExe = Join-Path $PreparedTorDirectory "tor.exe"
$PreparedGeoIp = Join-Path $PreparedDataDirectory "geoip"
$PreparedGeoIp6 = Join-Path $PreparedDataDirectory "geoip6"

Require-File $AppExe "Tauri executable"
Require-File $BackendExe "Backend sidecar"
Require-File $PreparedTorExe "Prepared Tor executable"
Require-File $PreparedGeoIp "Prepared Tor geoip data"
Require-File $PreparedGeoIp6 "Prepared Tor geoip6 data"

# Tauri consumes resources/tor and resources/data when creating installers, but the raw
# target/release directory is not a complete portable layout. Stage those verified
# resources beside the raw executable for the portable ZIP and launch smoke test.
$TargetTorDirectory = Join-Path $Target "tor"
$TargetDataDirectory = Join-Path $Target "data"
Stage-Directory $PreparedTorDirectory $TargetTorDirectory "Prepared Tor runtime"
Stage-Directory $PreparedDataDirectory $TargetDataDirectory "Prepared Tor data"

$TorExe = Join-Path $TargetTorDirectory "tor.exe"
$GeoIp = Join-Path $TargetDataDirectory "geoip"
$GeoIp6 = Join-Path $TargetDataDirectory "geoip6"
Require-File $TorExe "Staged Tor executable"
Require-File $GeoIp "Staged Tor geoip data"
Require-File $GeoIp6 "Staged Tor geoip6 data"

$Dlls = @(Get-ChildItem -LiteralPath $TargetTorDirectory -Filter "*.dll" -File)
if ($Dlls.Count -eq 0) {
    Write-Host "[INFO] Packaged Tor runtime has no adjacent DLLs; validating tor.exe directly."
} else {
    Write-Host "[INFO] Packaged Tor runtime includes $($Dlls.Count) adjacent DLL file(s)."
}

$Ping = (& $BackendExe --command ping | Out-String).Trim() | ConvertFrom-Json
if ($Ping.status -ne "MutinyChat backend alive") {
    throw "Packaged backend ping returned an unexpected response"
}
$TorVersion = (& $TorExe --version | Out-String).Trim()
if ($LASTEXITCODE -ne 0) {
    throw "Packaged Tor version smoke test failed"
}
if ([string]::IsNullOrWhiteSpace($TorVersion) -or $TorVersion -notmatch "Tor version") {
    throw "Packaged Tor executable returned an unexpected version response: $TorVersion"
}
Write-Host $TorVersion

$Nsis = @(Get-ChildItem -LiteralPath (Join-Path $Target "bundle\nsis") -Filter "*.exe" -File -ErrorAction SilentlyContinue)
if ($Nsis.Count -eq 0) {
    throw "NSIS installer was not produced"
}
$Msi = @(Get-ChildItem -LiteralPath (Join-Path $Target "bundle\msi") -Filter "*.msi" -File -ErrorAction SilentlyContinue)
if ($Msi.Count -eq 0) {
    Write-Warning "MSI installer was not produced; NSIS remains the required installer"
}

if (Test-Path -LiteralPath $Output) {
    Remove-Item -LiteralPath $Output -Recurse -Force
}
New-Item -ItemType Directory -Path $PortableRoot -Force | Out-Null
Copy-Item -LiteralPath $AppExe -Destination $PortableRoot
Copy-Item -LiteralPath $BackendExe -Destination $PortableRoot
Copy-Item -LiteralPath $TargetTorDirectory -Destination $PortableRoot -Recurse
Copy-Item -LiteralPath $TargetDataDirectory -Destination $PortableRoot -Recurse

$PortableTorExe = Join-Path $PortableRoot "tor\tor.exe"
$PortableBackendExe = Join-Path $PortableRoot "mutinychat-backend.exe"
Require-File $PortableTorExe "Portable Tor executable"
Require-File $PortableBackendExe "Portable backend sidecar"

$PortablePing = (& $PortableBackendExe --command ping | Out-String).Trim() | ConvertFrom-Json
if ($PortablePing.status -ne "MutinyChat backend alive") {
    throw "Portable backend ping returned an unexpected response"
}
$PortableTorVersion = (& $PortableTorExe --version | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or $PortableTorVersion -notmatch "Tor version") {
    throw "Portable Tor version smoke test failed"
}

$Forbidden = @(".venv", ".venv-windows-build", "__pycache__", "target\debug", "backend\build")
foreach ($Pattern in $Forbidden) {
    if (Get-ChildItem -LiteralPath $PortableRoot -Recurse -Force | Where-Object { $_.FullName -like "*$Pattern*" }) {
        throw "Portable package contains forbidden development content: $Pattern"
    }
}

$PortableZip = Join-Path $Output "MutinyChat_0.1.0_windows_x86_64_portable.zip"
Compress-Archive -Path (Join-Path $PortableRoot "*") -DestinationPath $PortableZip -CompressionLevel Optimal
Require-File $PortableZip "Portable ZIP"

foreach ($Installer in $Nsis + $Msi) {
    Copy-Item -LiteralPath $Installer.FullName -Destination $Output
}

$ReleaseFiles = @(Get-ChildItem -LiteralPath $Output -File)
$ChecksumPath = Join-Path $Output "SHA256SUMS.txt"
$ChecksumLines = foreach ($File in $ReleaseFiles) {
    $Hash = (Get-FileHash -LiteralPath $File.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    "$Hash  $($File.Name)"
}
Set-Content -LiteralPath $ChecksumPath -Value $ChecksumLines -Encoding ascii

Write-Host "[OK] Verified Windows runtime and installer contents"
Get-ChildItem -LiteralPath $Output -File | Select-Object Name, Length | Format-Table -AutoSize