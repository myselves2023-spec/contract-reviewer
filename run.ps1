# 启动脚本：自动挑选一个「装了 python-docx」的 Python
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$port = if ($args.Count -ge 1) { $args[0] } else { "8765" }

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
    Write-Host ""
    Write-Host "未找到可用的 Python（需要 3.9+ 且已安装 python-docx）。" -ForegroundColor Yellow
    Write-Host "请先执行： python -m pip install python-docx" -ForegroundColor Yellow
    Write-Host ""
    exit 1
}

Write-Host "使用解释器： $python" -ForegroundColor DarkGray
& $python main.py --port $port
