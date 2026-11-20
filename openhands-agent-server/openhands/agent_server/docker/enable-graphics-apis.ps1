$ErrorActionPreference = "Stop"

$destinationDirectory = if ($env:OH_GPU_RUNTIME_PATH) {
    $env:OH_GPU_RUNTIME_PATH
} else {
    "C:\AgentServer\gpu"
}
New-Item -ItemType Directory -Force $destinationDirectory | Out-Null

function Copy-DriverFiles {
    param(
        [Parameter(Mandatory = $true)]
        [string] $SourceDirectory,
        [Parameter(Mandatory = $true)]
        [string[]] $Filenames,
        [hashtable] $Rename = @{}
    )

    foreach ($filename in $Filenames) {
        $source = Join-Path $SourceDirectory $filename
        $destinationName = if ($Rename.ContainsKey($filename)) {
            $Rename[$filename]
        } else {
            $filename
        }
        $destination = Join-Path $destinationDirectory $destinationName

        if (Test-Path $source) {
            $temporary = Join-Path `
                $destinationDirectory `
                (".$destinationName.$PID.$([guid]::NewGuid().ToString('N')).tmp")
            try {
                Copy-Item -Path $source -Destination $temporary -Force
                Move-Item -Path $temporary -Destination $destination -Force
            } finally {
                Remove-Item -Path $temporary -Force -ErrorAction SilentlyContinue
            }
        } else {
            Write-Warning "GPU driver file is unavailable: $source"
        }
    }
}

$driverStore = if ($env:OH_HOST_DRIVER_STORE_PATH) {
    $env:OH_HOST_DRIVER_STORE_PATH
} else {
    "C:\Windows\System32\HostDriverStore\FileRepository"
}
if (-not (Test-Path $driverStore)) {
    exit 0
}

$nvidiaSentinel = Get-ChildItem `
    "$driverStore\nv*.inf_amd64_*\nvapi64.dll" `
    -ErrorAction SilentlyContinue | `
    Select-Object -First 1
if ($nvidiaSentinel) {
    $nvidiaDirectory = $nvidiaSentinel.DirectoryName
    Copy-DriverFiles $nvidiaDirectory @(
        "nvapi64.dll",
        "nvEncodeAPI64.dll",
        "nvEncMFTH264x.dll",
        "nvEncMFThevcx.dll",
        "nvDecMFTMjpeg.dll",
        "nvDecMFTMjpegx.dll",
        "nvptxJitCompiler64.dll"
    )
    Copy-DriverFiles `
        $nvidiaDirectory `
        @("nvcuvid64.dll", "nvcuda64.dll", "nvcuda_loader64.dll") `
        @{
            "nvcuvid64.dll" = "nvcuvid.dll"
            "nvcuda_loader64.dll" = "nvcuda.dll"
        }
}

$amdSentinel = Get-ChildItem `
    "$driverStore\u*.inf_amd64_*\*\aticfx64.dll" `
    -ErrorAction SilentlyContinue | `
    Select-Object -First 1
if ($amdSentinel) {
    Copy-DriverFiles $amdSentinel.DirectoryName @(
        "aticfx64.dll",
        "atidxx64.dll",
        "atiadlxx.dll",
        "atiadlxy.dll",
        "amfrt64.dll",
        "amfrtdrv64.dll",
        "amdihk64.dll"
    )
}
