param([Parameter(Mandatory=$true)][string]$BackupPath)
$ErrorActionPreference = 'Stop'
$BackupPath = (Resolve-Path $BackupPath).Path
$Info = Get-Content (Join-Path $BackupPath 'manifest.json') -Raw | ConvertFrom-Json
$ProjectPath = $Info.project
foreach ($Item in $Info.files) {
    if ($Item.path -match '\.\.' -or [System.IO.Path]::IsPathRooted($Item.path)) { throw 'Unsafe backup manifest.' }
    $Target = Join-Path $ProjectPath $Item.path
    if (Test-Path $Target) { Remove-Item -LiteralPath $Target -Recurse -Force }
    if ($Item.existed) {
        New-Item -ItemType Directory -Path (Split-Path $Target -Parent) -Force | Out-Null
        Copy-Item -LiteralPath (Join-Path $BackupPath $Item.path) -Destination $Target -Recurse -Force
    }
}
Write-Host "Restored project files at $ProjectPath. SDK/NDK/Gradle caches were not changed."
Write-Host "Next: cd $ProjectPath ; flutter pub get"
