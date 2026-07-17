param(
    [string]$TorBrowserVersion = "15.0.18",
    [string]$TorSigningFingerprint = "EF6E286DDA85EA2A4BA7DE684E2C6E8793298290"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ResourceRoot = Join-Path $Root "src-tauri\resources"
$TorDestination = Join-Path $ResourceRoot "tor"
$DataDestination = Join-Path $ResourceRoot "data"
$Work = Join-Path $Root ".tor-windows-build"
$ArchiveName = "tor-expert-bundle-windows-x86_64-$TorBrowserVersion.tar.gz"
$BaseUrl = "https://archive.torproject.org/tor-package-archive/torbrowser/$TorBrowserVersion"
$ArchiveUrl = "$BaseUrl/$ArchiveName"
$SignatureUrl = "$ArchiveUrl.asc"
$ArchivePath = Join-Path $Work $ArchiveName
$SignaturePath = "$ArchivePath.asc"
$ExtractPath = Join-Path $Work "extracted"

function Assert-LastExitCode([string]$Activity) {
    if ($LASTEXITCODE -ne 0) {
        throw "$Activity failed with exit code $LASTEXITCODE"
    }
}

if (-not (Get-Command tar.exe -ErrorAction SilentlyContinue)) {
    throw "tar.exe is required to extract the official Tor Expert Bundle"
}
if (-not (Get-Command gpg.exe -ErrorAction SilentlyContinue)) {
    throw "gpg.exe is required to verify the official Tor signature"
}

if (Test-Path -LiteralPath $Work) {
    Remove-Item -LiteralPath $Work -Recurse -Force
}
New-Item -ItemType Directory -Path $Work -Force | Out-Null
New-Item -ItemType Directory -Path $ExtractPath -Force | Out-Null

Write-Host "[INFO] Downloading official Tor Expert Bundle $TorBrowserVersion..."
Invoke-WebRequest -Uri $ArchiveUrl -OutFile $ArchivePath
Invoke-WebRequest -Uri $SignatureUrl -OutFile $SignaturePath

Write-Host "[INFO] Importing the Tor Browser Developers signing key..."
& gpg.exe --batch --keyserver hkps://keys.openpgp.org --recv-keys $TorSigningFingerprint
Assert-LastExitCode "Tor signing-key import"

$FingerprintOutput = (& gpg.exe --batch --with-colons --fingerprint $TorSigningFingerprint | Out-String)
Assert-LastExitCode "Tor signing-key fingerprint check"
if ($FingerprintOutput -notmatch $TorSigningFingerprint) {
    throw "Imported key did not match the pinned Tor signing fingerprint"
}

Write-Host "[INFO] Verifying Tor archive signature..."
& gpg.exe --batch --verify $SignaturePath $ArchivePath
Assert-LastExitCode "Tor archive signature verification"

& tar.exe -xzf $ArchivePath -C $ExtractPath
Assert-LastExitCode "Tor archive extraction"

$TorExe = Get-ChildItem -LiteralPath $ExtractPath -Filter "tor.exe" -File -Recurse | Select-Object -First 1
if (-not $TorExe) {
    throw "The verified Tor archive did not contain tor.exe"
}
$TorSource = $TorExe.Directory.FullName
$DataSource = Get-ChildItem -LiteralPath $ExtractPath -Directory -Recurse |
    Where-Object { (Test-Path (Join-Path $_.FullName "geoip")) -and (Test-Path (Join-Path $_.FullName "geoip6")) } |
    Select-Object -First 1
if (-not $DataSource) {
    throw "The verified Tor archive did not contain geoip and geoip6 data"
}

foreach ($Destination in @($TorDestination, $DataDestination)) {
    if (Test-Path -LiteralPath $Destination) {
        Remove-Item -LiteralPath $Destination -Recurse -Force
    }
    New-Item -ItemType Directory -Path $Destination -Force | Out-Null
}

Copy-Item -Path (Join-Path $TorSource "*") -Destination $TorDestination -Recurse -Force
Copy-Item -Path (Join-Path $DataSource.FullName "*") -Destination $DataDestination -Recurse -Force

$BundledTor = Join-Path $TorDestination "tor.exe"
if (-not (Test-Path -LiteralPath $BundledTor -PathType Leaf)) {
    throw "Prepared Tor runtime is missing tor.exe"
}
foreach ($GeoIpFile in @("geoip", "geoip6")) {
    if (-not (Test-Path -LiteralPath (Join-Path $DataDestination $GeoIpFile) -PathType Leaf)) {
        throw "Prepared Tor runtime is missing $GeoIpFile"
    }
}

$Dlls = @(Get-ChildItem -LiteralPath $TorDestination -Filter "*.dll" -File)
if ($Dlls.Count -eq 0) {
    Write-Host "[INFO] Tor bundle contains no adjacent DLLs; validating the self-contained executable directly."
} else {
    Write-Host "[INFO] Tor bundle includes $($Dlls.Count) adjacent DLL file(s)."
}

$VersionOutput = (& $BundledTor --version | Out-String).Trim()
Assert-LastExitCode "Bundled Tor version smoke test"
if ([string]::IsNullOrWhiteSpace($VersionOutput) -or $VersionOutput -notmatch "Tor version") {
    throw "Bundled Tor executable returned an unexpected version response: $VersionOutput"
}
Write-Host "[OK] $VersionOutput"
Write-Host "[OK] Verified source: $ArchiveUrl"
Write-Host "[OK] Signing fingerprint: $TorSigningFingerprint"
