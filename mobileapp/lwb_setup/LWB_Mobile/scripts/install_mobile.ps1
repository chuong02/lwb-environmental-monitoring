param([string]$ProjectPath = 'C:\lwb_mobile', [switch]$SkipChecks)
$ErrorActionPreference = 'Stop'
$Bundle = Split-Path $PSScriptRoot -Parent
$Source = Join-Path $Bundle 'mobile'
$ProjectPath = (Resolve-Path $ProjectPath).Path
$Pubspec = Join-Path $ProjectPath 'pubspec.yaml'
if (!(Test-Path $Pubspec)) { throw "No pubspec.yaml in $ProjectPath" }
if ((Get-Content $Pubspec -Raw) -notmatch '(?m)^name:\s*lwb_mobile\s*$') {
    throw 'This installer expects the existing project name lwb_mobile. Nothing changed.'
}
Get-Command flutter -ErrorAction Stop | Out-Null
$Backup = Join-Path (Split-Path $ProjectPath -Parent) ('lwb_mobile_backup_' + (Get-Date -Format 'yyyyMMdd_HHmmss_fff'))
New-Item -ItemType Directory -Path $Backup -Force | Out-Null
$Tracked = @('lib','test','pubspec.yaml','pubspec.lock','android/app/src/main/AndroidManifest.xml',
 'android/app/src/debug/AndroidManifest.xml','android/app/src/debug/res/xml/lwb_debug_network_security.xml')
$Manifest = @()
foreach ($Rel in $Tracked) {
    $File = Join-Path $ProjectPath $Rel
    $Exists = Test-Path $File
    $Manifest += [pscustomobject]@{path=$Rel; existed=$Exists}
    if ($Exists) {
        $Target = Join-Path $Backup $Rel
        New-Item -ItemType Directory -Path (Split-Path $Target -Parent) -Force | Out-Null
        Copy-Item -LiteralPath $File -Destination $Target -Recurse -Force
    }
}
@{project=$ProjectPath; files=$Manifest} | ConvertTo-Json -Depth 6 |
    Set-Content (Join-Path $Backup 'manifest.json') -Encoding UTF8
Write-Host "Backup created: $Backup" -ForegroundColor Cyan
Write-Host 'Stop flutter run / Android Studio Run before continuing.' -ForegroundColor Yellow
foreach ($Folder in @('lib','test')) {
    $From = Join-Path $Source $Folder
    Get-ChildItem -LiteralPath $From -Recurse -File | ForEach-Object {
        $Rel = $_.FullName.Substring($Source.Length + 1)
        $Dest = Join-Path $ProjectPath $Rel
        New-Item -ItemType Directory -Path (Split-Path $Dest -Parent) -Force | Out-Null
        Copy-Item -LiteralPath $_.FullName -Destination $Dest -Force
    }
}
$DemoTest = Join-Path $ProjectPath 'test/widget_test.dart'
if (Test-Path $DemoTest) {
    $Text = Get-Content $DemoTest -Raw
    if ($Text -match 'Counter increments smoke test' -or $Text -match 'counter increments') {
        Move-Item $DemoTest ($DemoTest + '.demo-backup') -Force
    }
}
$AndroidNs = 'http://schemas.android.com/apk/res/android'
function Set-AndroidAttribute($Document, $Node, $Name, $Value) {
    $Attr = $Document.CreateAttribute('android', $Name, $AndroidNs)
    $Attr.Value = $Value
    $Node.Attributes.SetNamedItem($Attr) | Out-Null
}
$MainPath = Join-Path $ProjectPath 'android/app/src/main/AndroidManifest.xml'
[xml]$Main = Get-Content $MainPath -Raw
$HasInternet = @($Main.manifest.'uses-permission') | Where-Object {
    $_ -and $_.GetAttribute('name', $AndroidNs) -eq 'android.permission.INTERNET'
}
if (!$HasInternet) {
    $Permission = $Main.CreateElement('uses-permission')
    Set-AndroidAttribute $Main $Permission 'name' 'android.permission.INTERNET'
    $Main.manifest.AppendChild($Permission) | Out-Null
    $Main.Save($MainPath)
}
$DebugPath = Join-Path $ProjectPath 'android/app/src/debug/AndroidManifest.xml'
if (Test-Path $DebugPath) { [xml]$Debug = Get-Content $DebugPath -Raw }
else { [xml]$Debug = '<manifest xmlns:android="http://schemas.android.com/apk/res/android"></manifest>' }
$Application = $Debug.SelectSingleNode('/manifest/application')
if ($null -eq $Application) {
    $Application = $Debug.CreateElement('application')
    $Debug.manifest.AppendChild($Application) | Out-Null
}
Set-AndroidAttribute $Debug $Application 'networkSecurityConfig' '@xml/lwb_debug_network_security'
New-Item -ItemType Directory -Path (Split-Path $DebugPath -Parent) -Force | Out-Null
$Debug.Save($DebugPath)
$SecurityPath = Join-Path $ProjectPath 'android/app/src/debug/res/xml/lwb_debug_network_security.xml'
New-Item -ItemType Directory -Path (Split-Path $SecurityPath -Parent) -Force | Out-Null
@'
<?xml version="1.0" encoding="utf-8"?>
<network-security-config>
    <base-config cleartextTrafficPermitted="false" />
    <domain-config cleartextTrafficPermitted="true">
        <domain>10.0.2.2</domain>
        <domain>127.0.0.1</domain>
        <domain>localhost</domain>
    </domain-config>
</network-security-config>
'@ | Set-Content $SecurityPath -Encoding UTF8
Push-Location $ProjectPath
try {
    & flutter pub add 'http:^1.6.0' 'shared_preferences:^2.5.3'
    if ($LASTEXITCODE -ne 0) { throw 'flutter pub add failed. Backup is available above.' }
    & dart format lib test/lwb_v1
    if ($LASTEXITCODE -ne 0) { throw 'Dart formatting failed; inspect reported source location.' }
    if (!$SkipChecks) {
        & flutter analyze --no-fatal-infos
        if ($LASTEXITCODE -ne 0) { throw 'Analyzer reported problems. Do not run the app until these are reviewed.' }
        & flutter test test/lwb_v1
        if ($LASTEXITCODE -ne 0) { throw 'Tests did not pass. Send the failing test output for diagnosis.' }
    }
} finally { Pop-Location }
Write-Host 'Installed. No SDK/NDK/Gradle file was changed.' -ForegroundColor Green
Write-Host "cd $ProjectPath"
Write-Host 'flutter run -d emulator-5554'
