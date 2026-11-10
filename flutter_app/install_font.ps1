$ErrorActionPreference = 'Stop'
$fontDir = Join-Path $PSScriptRoot 'assets/fonts'
New-Item -ItemType Directory -Force -Path $fontDir | Out-Null
$fontTemp = Join-Path $fontDir 'NotoSansKR.download'
$licenseTemp = Join-Path $fontDir 'OFL.download'
try {
    Invoke-WebRequest -UseBasicParsing -Uri 'https://raw.githubusercontent.com/google/fonts/main/ofl/notosanskr/NotoSansKR%5Bwght%5D.ttf' -OutFile $fontTemp
    Invoke-WebRequest -UseBasicParsing -Uri 'https://raw.githubusercontent.com/google/fonts/main/ofl/notosanskr/OFL.txt' -OutFile $licenseTemp
    $bytes = [System.IO.File]::ReadAllBytes($fontTemp)
    if ($bytes.Length -lt 100000 -or $bytes[0] -ne 0 -or $bytes[1] -ne 1 -or $bytes[2] -ne 0 -or $bytes[3] -ne 0) {
        throw 'Downloaded file is not a valid TrueType font.'
    }
    Move-Item -Force $fontTemp (Join-Path $fontDir 'NotoSansKR.ttf')
    Move-Item -Force $licenseTemp (Join-Path $fontDir 'OFL.txt')
    Write-Host 'Font installed. Run: flutter pub get'
} finally {
    Remove-Item $fontTemp, $licenseTemp -Force -ErrorAction SilentlyContinue
}
