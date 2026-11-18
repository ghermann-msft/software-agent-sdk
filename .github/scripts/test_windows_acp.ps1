param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('codex', 'copilot')]
    [string]$Provider,

    [int]$TimeoutSeconds = 90
)

$ErrorActionPreference = 'Stop'

if ($Provider -eq 'codex') {
    $command = 'C:\ACP\codex-acp.cmd'
    $arguments = @()
} else {
    $command = 'C:\Copilot\copilot.exe'
    $arguments = @('--acp', '--stdio', '--no-auto-update')
}

$startInfo = New-Object System.Diagnostics.ProcessStartInfo
$startInfo.FileName = $command
$startInfo.Arguments = [string]::Join(' ', [string[]]$arguments)
$startInfo.UseShellExecute = $false
$startInfo.CreateNoWindow = $true
$startInfo.RedirectStandardInput = $true
$startInfo.RedirectStandardOutput = $true
$startInfo.RedirectStandardError = $true

$process = [System.Diagnostics.Process]::Start($startInfo)
$request = @{
    jsonrpc = '2.0'
    id = 1
    method = 'initialize'
    params = @{
        protocolVersion = 1
        clientCapabilities = @{}
        clientInfo = @{
            name = 'openhands-windows-smoke'
            version = '1.0.0'
        }
    }
} | ConvertTo-Json -Compress -Depth 4

try {
    $process.StandardInput.WriteLine($request)
    $process.StandardInput.Flush()
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)

    while ([DateTime]::UtcNow -lt $deadline) {
        $remaining = [int]($deadline - [DateTime]::UtcNow).TotalMilliseconds
        $read = $process.StandardOutput.ReadLineAsync()
        if (-not $read.Wait([Math]::Max(1, $remaining))) {
            break
        }
        $line = $read.Result
        if ($null -eq $line) {
            break
        }
        if (-not $line.StartsWith('{')) {
            continue
        }

        $response = $line | ConvertFrom-Json
        if ($response.id -eq 1 -and $null -ne $response.result.agentInfo.name) {
            Write-Host (
                'ACP initialize succeeded for {0}: {1} {2}' -f
                $Provider,
                $response.result.agentInfo.name,
                $response.result.agentInfo.version
            )
            exit 0
        }
    }

    if (-not $process.HasExited) {
        $process.Kill()
        $process.WaitForExit()
    }
    $stderr = $process.StandardError.ReadToEnd()
    throw "ACP initialize timed out for ${Provider}: $stderr"
} finally {
    if (-not $process.HasExited) {
        $process.Kill()
        $process.WaitForExit()
    }
    $process.Dispose()
}
