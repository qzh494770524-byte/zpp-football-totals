$ErrorActionPreference = 'Stop'
$taskName = 'Nowgoal_Totals_Analysis_20260910_1921'
$workspace = 'C:\Users\Administrator\Desktop\zpp'
$pythonWindowless = 'C:\Users\Administrator\AppData\Local\Programs\Python\Python312\pythonw.exe'
$runner = Join-Path $workspace 'run_totals_analysis.py'
$runAt = [datetime]::ParseExact('2026-09-10 19:21:00', 'yyyy-MM-dd HH:mm:ss', [Globalization.CultureInfo]::InvariantCulture)
if (-not (Test-Path -LiteralPath $pythonWindowless) -or -not (Test-Path -LiteralPath $runner)) {
    throw 'Python or the prepared analysis runner is missing.'
}
$action = New-ScheduledTaskAction -Execute $pythonWindowless -Argument ('"' + $runner + '"') -WorkingDirectory $workspace
$trigger = New-ScheduledTaskTrigger -Once -At $runAt
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -WakeToRun -ExecutionTimeLimit (New-TimeSpan -Hours 2) -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existing -and ($existing.Actions.Execute -ne $pythonWindowless -or $existing.Actions.Arguments -notlike '*run_totals_analysis.py*')) {
    throw 'A different task already uses this name. It has not been modified.'
}
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description 'Analyze the latest local Nowgoal multi-bookmaker dataset once at 19:21 China time on September 10, 2026.' -Force | Out-Null
$registered = Get-ScheduledTask -TaskName $taskName
$info = Get-ScheduledTaskInfo -TaskName $taskName
$config = [ordered]@{
    task_name = $taskName
    run_at = '2026-09-10T19:21:00+08:00'
    timezone = 'Asia/Shanghai'
    frequency = 'once'
    state = $registered.State.ToString()
    next_run = $info.NextRunTime.ToString('yyyy-MM-dd HH:mm:ss zzz')
    executable = $registered.Actions.Execute
    arguments = $registered.Actions.Arguments
    output_index = (Join-Path $workspace 'analysis\最新自动分析.html')
    requires_logged_in_user = $true
    start_when_available = $registered.Settings.StartWhenAvailable
}
$json = $config | ConvertTo-Json -Depth 4
[IO.File]::WriteAllText((Join-Path $workspace 'analysis\automation_schedule.json'), $json, [Text.UTF8Encoding]::new($false))
$json
