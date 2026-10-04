param([string]$Instance = $env:AMBIENT_BRIGHTNESS_INSTANCE, [int]$Level = $(if($env:AMBIENT_BRIGHTNESS_LEVEL){[int]$env:AMBIENT_BRIGHTNESS_LEVEL}else{-1}))
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$methods = @(Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods)
$monitors = @(Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightness | Where-Object { $_.InstanceName -in $methods.InstanceName })
if ($Level -ge 0) {
    if ($Level -gt 100 -or -not ($monitors | Where-Object InstanceName -eq $Instance)) { throw 'Unsupported monitor' }
    $method = $methods | Where-Object InstanceName -eq $Instance
    if (-not $method) { throw 'Monitor does not expose brightness control' }
    $result = Invoke-CimMethod -InputObject $method -MethodName WmiSetBrightness -Arguments @{Timeout=[uint32]1;Brightness=[byte]$Level}
    # Some monitor providers return no value after a successful WMI method.
    # Only an explicit non-zero status is an error; report the actual readback.
    if ($null -ne $result.ReturnValue -and $result.ReturnValue -ne 0) { throw 'Windows rejected brightness request' }
    $monitors = @(Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightness)
}
ConvertTo-Json -InputObject @($monitors | ForEach-Object { @{ id=$_.InstanceName; value=[int]$_.CurrentBrightness; name='Windows 内置屏幕' } }) -Compress
