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

function Require-File([string]$Path, [string]$Label) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "$Label is missing: $Path"
    }
}

$AppExe = Join-Path $Target "mutinychat.exe"
$BackendExe = Join-Path $Target "mutinychat-backend.exe"
$TorExe = Join-Path $Target "tor\tor.exe"
$GeoIp = Join-Path $Target "data\geoip"
$GeoIp6 = Join-Path $Target "data\geoip6"

Require-File $AppExe "Tauri executable"
Require-File $BackendExe "Backend sidecar"
Require-File $TorExe "Bundled Tor executable"
Require-File $GeoIp "Tor geoip data"
Require-File $GeoIp6 "Tor geoip6 data"

$Dlls = @(Get-ChildItem -LiteralPath (Split-Path $TorExe) -Filter "*.dll" -File)
if ($Dlls.Count -eq 0) {
    throw "Packaged Tor runtime contains no DLL files"
}

$Ping = (& $BackendExe --command ping | Out-String).Trim() | ConvertFrom-Json
if ($Ping.status -ne "MutinyChat backend alive") {
    throw "Packaged backend ping returned an unexpected response"
}
& $TorExe --version | Out-Host
if ($LASTEXITCODE -ne 0) {
    throw "Packaged Tor version smoke test failed"
}

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
Copy-Item -LiteralPath (Join-Path $Target "tor") -Destination $PortableRoot -Recurse
Copy-Item -LiteralPath (Join-Path $Target "data") -Destination $PortableRoot -Recurse

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
