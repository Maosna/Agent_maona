# Maona - Build Python embeddable backend
# Downloads Python embeddable, installs pip + dependencies
param(
    [string]$PythonVersion = "3.13.12",
    [string]$OutputDir = "build/python-dist"
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$ProjectRoot = Split-Path -Parent $PSScriptRoot

Set-Location $ProjectRoot
$OutputPath = Join-Path $ProjectRoot $OutputDir

# Skip if already built
if (Test-Path (Join-Path $OutputPath "python.exe")) {
    $existing = & (Join-Path $OutputPath "python.exe") --version 2>&1
    Write-Host "[build-py] Python already built: $existing - skipping"
    exit 0
}

Write-Host "[build-py] Building Python $PythonVersion embeddable..."

# Create output dir
New-Item -ItemType Directory -Force -Path $OutputPath | Out-Null

# Download Python embeddable
$url = "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-embed-amd64.zip"
$zipPath = Join-Path $ProjectRoot "build/python-embed.zip"
Write-Host "[build-py] Downloading $url ..."
Invoke-WebRequest -Uri $url -OutFile $zipPath

# Extract
Write-Host "[build-py] Extracting..."
Expand-Archive -Path $zipPath -DestinationPath $OutputPath -Force
Remove-Item $zipPath

# Enable site-packages: uncomment "import site" in ._pth file
$pthFile = Get-ChildItem -Path $OutputPath -Filter "python*._pth" | Select-Object -First 1
if ($pthFile) {
    $content = Get-Content $pthFile.FullName -Raw
    # Uncomment import site
    $content = $content -replace '#import site', 'import site'
    # Add Lib/site-packages path
    $content = $content -replace '(?m)^(import site)$', "Lib\site-packages`n`$1"
    Set-Content $pthFile.FullName $content -NoNewline
    Write-Host "[build-py] Enabled site-packages in $($pthFile.Name)"
}

$pythonExe = Join-Path $OutputPath "python.exe"

# Install pip
Write-Host "[build-py] Installing pip..."
$getPip = Join-Path $ProjectRoot "build/get-pip.py"
Invoke-WebRequest -Uri "https://bootstrap.pypa.io/get-pip.py" -OutFile $getPip
& $pythonExe $getPip --no-warn-script-location
Remove-Item $getPip

# Install backend dependencies
Write-Host "[build-py] Installing backend dependencies..."
$reqFile = Join-Path $ProjectRoot "backend/requirements.txt"
& $pythonExe -m pip install --no-warn-script-location -r $reqFile

# Verify
$ver = & $pythonExe --version 2>&1
$pkgs = & $pythonExe -m pip list 2>&1 | Out-String
Write-Host "[build-py] Done! $ver"
Write-Host "[build-py] Installed packages:"
$pkgs -split "`n" | Select-Object -First 15 | ForEach-Object { Write-Host "  $_" }

Write-Host ""
Write-Host "[build-py] Python backend ready at: $OutputPath"
