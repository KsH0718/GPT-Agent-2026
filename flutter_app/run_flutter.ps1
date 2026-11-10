# 이 스크립트가 있는 flutter_app 폴더로 이동
Set-Location -LiteralPath $PSScriptRoot

try {
    flutter pub get

    if ($LASTEXITCODE -ne 0) {
        throw "패키지를 준비하지 못했습니다."
    }

    flutter run -d chrome
}
finally {
    Write-Host "`nFlutter 종료 후 임시 폴더를 정리합니다."

    foreach ($folderName in @("build")) {
        $folderPath = Join-Path $PSScriptRoot $folderName

        # 종료 직후 잠금이 풀리는 데 시간이 걸릴 수 있어 재시도
        for ($attempt = 1; $attempt -le 5; $attempt++) {
            if (-not (Test-Path -LiteralPath $folderPath)) {
                break
            }

            try {
                Remove-Item -LiteralPath $folderPath `
                    -Recurse -Force -ErrorAction Stop

                Write-Host "$folderName 삭제 완료"
                break
            }
            catch {
                if ($attempt -eq 5) {
                    Write-Warning "$folderName 삭제 실패: $($_.Exception.Message)"
                }
                else {
                    Start-Sleep -Seconds 1
                }
            }
        }
    }
}