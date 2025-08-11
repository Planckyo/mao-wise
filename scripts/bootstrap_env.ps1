param(
  [string]$LibraryDir = "D:\桌面\本地PDF文献知识库"
)
$ErrorActionPreference = "Stop"
chcp 65001 > $null

$envPath = Join-Path (Get-Location) ".env"
if (-not (Test-Path $envPath)) { New-Item -ItemType File -Path $envPath | Out-Null }

# 读入并移除旧行
$content = Get-Content $envPath -Raw -ErrorAction SilentlyContinue
if ($content -match "(?m)^\s*MAOWISE_LIBRARY_DIR\s*=") {
  $content = ($content -split "`r?`n") | Where-Object {$_ -notmatch "(?m)^\s*MAOWISE_LIBRARY_DIR\s*="} | Out-String
}
# 追加新行（UTF-8）
$line = "MAOWISE_LIBRARY_DIR=$LibraryDir"
if ($content.Trim().Length -gt 0) { $content = $content.Trim() + "`r`n" + $line + "`r`n" } else { $content = $line + "`r`n" }
[System.IO.File]::WriteAllText($envPath, $content, [System.Text.UTF8Encoding]::new($false))
Write-Host "✅ .env updated: MAOWISE_LIBRARY_DIR=$LibraryDir"
