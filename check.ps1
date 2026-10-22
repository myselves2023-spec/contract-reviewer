# 检查 API Key 是否可用：只发一次最小请求
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$candidates = @()
$bundled = Join-Path $env:USERPROFILE ".dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
if (Test-Path $bundled) { $candidates += $bundled }
$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if ($pythonCmd) { $candidates += $pythonCmd.Source }

$python = $null
foreach ($candidate in $candidates) {
    & $candidate -c "import docx" 2>$null
    if ($LASTEXITCODE -eq 0) { $python = $candidate; break }
}

if (-not $python) {
    Write-Host "未找到可用的 Python（需要 3.9+ 且已安装 python-docx）。" -ForegroundColor Yellow
    exit 1
}

& $python tools\check_key.py
exit $LASTEXITCODE
