param([string]$RuntimeRoot = (Split-Path $PSScriptRoot -Parent))
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
function Initialize-InstallerHost {
    # PowerShell 7 parents may otherwise pass an incompatible PSModulePath to 5.1.
    foreach($module in @('Microsoft.PowerShell.Utility','Microsoft.PowerShell.Archive')) {
        Import-Module (Join-Path $PSHOME ("Modules/$module/$module.psd1")) -Force
    }
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
}
Initialize-InstallerHost
$runtimePath = [IO.Path]::GetFullPath($RuntimeRoot).TrimEnd('\','/')
function Assert-Owned([string]$Candidate) {
    $full=[IO.Path]::GetFullPath($Candidate)
    if(-not $full.StartsWith($runtimePath+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) { throw 'Runtime path boundary violation' }
    $current=$full
    while($current) {
        if(Test-Path -LiteralPath $current) {
            if((Get-Item -Force -LiteralPath $current).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Runtime paths must not use junctions or symbolic links' }
        }
        $current=Split-Path -Path $current -Parent
    }
    return $full
}
function Move-Owned([string]$Source,[string]$Destination) {
    $a=Assert-Owned $Source; $b=Assert-Owned $Destination
    Move-Item -LiteralPath $a -Destination $b
}
function Checked-Download([string]$Url,[string]$Destination,[string]$ChecksumUrl,[string]$ExpectedSha256) {
    if($ExpectedSha256) { $expected=$ExpectedSha256.ToLower() } else {
        $checksum=(Invoke-WebRequest -UseBasicParsing -Uri $ChecksumUrl).Content
        if($checksum -is [byte[]]) { $checksum=[Text.Encoding]::UTF8.GetString($checksum) }
        $expected=($checksum.Trim() -split '\s+')[0].ToLower()
    }
    if($expected -notmatch '^[a-f0-9]{64}$') { throw 'Invalid download checksum' }
    if((Test-Path -LiteralPath $Destination) -and (Get-FileHash -LiteralPath $Destination -Algorithm SHA256).Hash.ToLower() -eq $expected) { return }
    $partial=$Destination+'.part'
    Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile $partial
    if((Get-FileHash -LiteralPath $partial -Algorithm SHA256).Hash.ToLower() -ne $expected) { throw 'Download checksum mismatch' }
    Move-Item -LiteralPath $partial -Destination $Destination -Force
}
New-Item -ItemType Directory -Path $runtimePath -Force | Out-Null
if((Get-Item -LiteralPath $runtimePath).PSDrive.Free -lt 25GB) { throw 'Runtime installation or repair requires at least 25 GB free space' }
$installMarker=Assert-Owned (Join-Path $runtimePath '.runtime-installing')
Set-Location -LiteralPath $runtimePath
Set-Content -LiteralPath $installMarker -Value 'Dependency installation incomplete; retry on launch.' -Encoding ascii
$specPath=Join-Path $runtimePath 'scripts/runtime-spec.json'
$spec=Get-Content -Raw -LiteralPath $specPath | ConvertFrom-Json
if($spec.schema_version -ne 1) { throw 'Unsupported runtime specification' }
$downloads=Assert-Owned (Join-Path $runtimePath '.downloads')
$backup=Assert-Owned (Join-Path $runtimePath ('.runtime-backups/'+[DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss')+'-'+[guid]::NewGuid().ToString('N')))
New-Item -ItemType Directory -Path $downloads -Force | Out-Null
function Preserve-Previous([string]$Destination,[string]$Name) {
    if(Test-Path -LiteralPath $Destination) {
        New-Item -ItemType Directory -Path $backup -Force | Out-Null
        Move-Owned $Destination (Join-Path $backup $Name)
    }
}
function Install-Archive($Artifact,[string]$Name,[string]$Folder,[string]$ArchiveFolder) {
    Write-Host "Installing verified $Name..."
    $zip=Assert-Owned (Join-Path $downloads ($Name+'.zip'))
    Checked-Download $Artifact.url $zip '' $Artifact.sha256
    $unpack=Assert-Owned (Join-Path $downloads ($Name+'-'+[guid]::NewGuid().ToString('N')))
    Expand-Archive -LiteralPath $zip -DestinationPath $unpack
    $source=if($ArchiveFolder) { Join-Path $unpack $ArchiveFolder } else { $unpack }
    $destination=Assert-Owned (Join-Path $runtimePath $Folder)
    Preserve-Previous $destination $Name
    New-Item -ItemType Directory -Path (Split-Path $destination -Parent) -Force | Out-Null
    Move-Owned $source $destination
    return $destination
}
# Use our verified tools even when different versions happen to be on PATH.
$uvFolder=Install-Archive $spec.uv 'uv' 'tools/uv' ''
$uvExe=Join-Path $uvFolder 'uv.exe'
if((Get-FileHash -LiteralPath $uvExe -Algorithm SHA256).Hash.ToLower() -ne $spec.uv.executable_sha256) { throw 'uv executable checksum mismatch' }
$env:UV_PYTHON_INSTALL_DIR=Join-Path $runtimePath 'tools/python'
$env:UV_PYTHON_PREFERENCE='only-managed'
$env:UV_PYTHON_DOWNLOADS='automatic'
$env:UV_NO_PROGRESS='1'
$env:PYTHONUTF8='1'
Remove-Item Env:PYTHONHOME -ErrorAction SilentlyContinue
Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
foreach($name in @('ace','sa3')) {
    $artifact=$spec.sources.$name
    $folder=Install-Archive $artifact $name $artifact.folder $artifact.archive_folder
    $manifest=@(Get-ChildItem -LiteralPath $folder -Recurse -File -Force | ForEach-Object {
        @{path=$_.FullName.Substring($folder.Length+1).Replace('\','/');sha256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLower()}
    })
    [IO.File]::WriteAllText((Join-Path $folder '.source-manifest.json'),(ConvertTo-Json -InputObject $manifest -Depth 3),(New-Object Text.UTF8Encoding($false)))
    Set-Content -LiteralPath (Join-Path $folder '.source-revision') -Value $artifact.revision -Encoding ascii
}
Write-Output 'Installing pinned Python and ACE/backend dependencies (large downloads)...'
& $uvExe sync --project vendor/ACE-Step-1.5 --python $spec.python --frozen --no-dev
if($LASTEXITCODE) { throw 'ACE environment installation failed' }
$basePython=Join-Path $runtimePath $spec.environments.base.executable
& $uvExe pip install --python $basePython --require-hashes -r scripts/runtime-backend.lock
if($LASTEXITCODE) { throw 'Backend dependencies failed' }
Write-Output 'Installing isolated SA3 runtime...'
Preserve-Previous (Join-Path $runtimePath '.venv-sa3-py311') 'sa3-environment'
& $uvExe venv .venv-sa3-py311 --python $spec.python
if($LASTEXITCODE) { throw 'SA3 Python installation failed' }
$saPython=Join-Path $runtimePath $spec.environments.sa3.executable
& $uvExe pip install --python $saPython --require-hashes --index-strategy unsafe-best-match -r scripts/runtime-sa3.lock
if($LASTEXITCODE) { throw 'SA3 dependencies failed' }
& $uvExe pip install --python $saPython --no-deps -e vendor/stable-audio-3
if($LASTEXITCODE) { throw 'SA3 source installation failed' }
$null=Install-Archive $spec.ffmpeg 'ffmpeg' 'tools/ffmpeg' ('ffmpeg-'+$spec.ffmpeg.version+'-essentials_build')
Write-Output 'Checking source hashes, dependency integrity, imports, FFmpeg and CUDA device 0...'
& $basePython scripts/runtime_health.py --root $runtimePath --spec $specPath --complete-install
if($LASTEXITCODE) { throw 'Runtime health validation failed; repair is required' }
Remove-Item -LiteralPath $installMarker
Write-Output 'Runtime ready. Model weights will be configured in the first-run wizard.'
