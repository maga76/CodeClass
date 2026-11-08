# Сборка программы и установщика:  powershell -ExecutionPolicy Bypass -File desktop\build_exe.ps1
# Результат: desktop\installer\CodeClass-Setup-1.0.0.exe (и папка desktop\dist\CodeClass без установки)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$python = Join-Path $PSScriptRoot '..\.venv\Scripts\python.exe'

& $python -m pip install -q -r ..\requirements.txt -r requirements.txt
& $python -m PyInstaller --noconfirm --clean CodeClass.spec
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller завершился с ошибкой' }

$iscc = @(
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if ($iscc) {
    & $iscc /Q installer.iss
    if ($LASTEXITCODE -ne 0) { throw 'Inno Setup завершился с ошибкой' }
    Write-Host "Установщик: $PSScriptRoot\installer\CodeClass-Setup-1.0.0.exe"
} else {
    Write-Host 'Inno Setup не найден (winget install JRSoftware.InnoSetup) — установщик не собран.'
}
Write-Host "Программа без установки: $PSScriptRoot\dist\CodeClass\CodeClass.exe"
