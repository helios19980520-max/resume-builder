<#
  Deploy the resume builder to a remote Linux server from Windows.
  Run from the folder that contains this repo's zip OR from inside the repo folder:

    powershell -ExecutionPolicy Bypass -File deploy\deploy.ps1 -Server hades-server
    powershell -ExecutionPolicy Bypass -File deploy\deploy.ps1 -Server hades-server -Port 3000 -EnvFile .\.env

  -Server   an alias from ~/.ssh/config (e.g. hades-server) or user@hostname
  -Port     public port for the web UI on the server (default 80)
  -EnvFile  local .env to upload (keys). If omitted and the server has no .env, you'll be told to edit it there.
  -Zip      path to a resume-builder .tgz or .zip; if omitted the script packs the current repo folder.
#>
param(
  [Parameter(Mandatory = $true)][string]$Server,
  [int]$Port = 80,
  [string]$EnvFile = "",
  [string]$Zip = ""
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)   # repo root

if (-not $Zip) {
  $Zip = Join-Path $env:TEMP "resume-builder.tgz"
  Write-Host "==> Packing $root -> $Zip"
  if (Test-Path $Zip) { Remove-Item $Zip }
  $stage = Join-Path $env:TEMP "rb-stage"
  if (Test-Path $stage) { Remove-Item -Recurse -Force $stage }
  New-Item -ItemType Directory -Path (Join-Path $stage "resume-builder") | Out-Null
  robocopy $root (Join-Path $stage "resume-builder") /E /XD node_modules dist data __pycache__ .git /XF .env tsconfig.tsbuildinfo /NFL /NDL /NJH /NJS /NC /NS /NP | Out-Null
  # tar.exe (built into Windows 10+) writes forward slashes; Compress-Archive writes backslashes that break Linux unzip
  tar -czf $Zip -C $stage resume-builder
}

Write-Host "==> Uploading zip + setup script to $Server"
scp -q $Zip "${Server}:~/resume-builder.tgz"
scp -q (Join-Path $root "deploy\server-setup.sh") "${Server}:~/server-setup.sh"
if ($EnvFile) {
  Write-Host "==> Uploading $EnvFile as ~/resume-builder/.env"
  ssh $Server "mkdir -p ~/resume-builder"
  scp -q $EnvFile "${Server}:~/resume-builder/.env"
}

Write-Host "==> Running setup on the server (this can take several minutes on first run)"
ssh -t $Server "sed -i 's/\r$//' ~/server-setup.sh && bash ~/server-setup.sh ~/resume-builder.tgz $Port"
