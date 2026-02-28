param(
  [string]$PythonExe = "py"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Push-Location (Join-Path $PSScriptRoot "..")
try {
  if (-not (Get-Command $PythonExe -ErrorAction SilentlyContinue)) {
    Write-Error "未找到 Python 启动器（py），请安装 Python for Windows"
  }
  & $PythonExe -m pip install --upgrade pip setuptools wheel
  & $PythonExe -m pip install pyinstaller
  if (Test-Path "build") { Remove-Item -Recurse -Force "build" }
  if (Test-Path "dist\FundValuationWatcher") { Remove-Item -Recurse -Force "dist\FundValuationWatcher" }
  & $PythonExe -m PyInstaller -y FundValuationWatcher.spec
  Write-Host "已生成 dist\FundValuationWatcher\FundValuationWatcher.exe"
} finally {
  Pop-Location
}

