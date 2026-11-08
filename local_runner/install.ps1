# 노트북 작업 스케줄러 등록 (관리자 PowerShell 에서 실행: 로그온 여부와 관계없이 실행하려면 관리자 권한 필요)
#   powershell -ExecutionPolicy Bypass -File C:\auction_pc\ML\local_runner\install.ps1
# 03:00 night(법원자료→예측→웹페이지→push) / 06:00 outfit / 08:00 brief
# 절전이어도 깨움(WakeToRun, 전원 연결 시), 놓친 예약은 켜지자마자(StartWhenAvailable), 로그온 무관(S4U: 비밀번호 저장 안 함)
# -Interactive: 관리자 없이 등록 (로그온된 동안만 실행 — 화면 잠금·절전은 OK, 로그아웃/재부팅 후 미로그온이면 안 돎)
param([string]$User = "$env:USERDOMAIN\$env:USERNAME", [switch]$Interactive)

$ErrorActionPreference = 'Stop'
$runner = Join-Path $PSScriptRoot 'run_all.py'
$py = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $py) { $py = "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe" }
if (-not (Test-Path $py)) { throw "python.exe 없음" }

$jobs = @(
    @{ Name = 'ML_Night';  At = '03:00'; Arg = 'night';  Limit = 6 },
    @{ Name = 'ML_Outfit'; At = '06:00'; Arg = 'outfit'; Limit = 1 },
    @{ Name = 'ML_Brief';  At = '08:00'; Arg = 'brief';  Limit = 1 }
)
$logon = if ($Interactive) { 'Interactive' } else { 'S4U' }
$principal = New-ScheduledTaskPrincipal -UserId $User -LogonType $logon -RunLevel Limited
if ($Interactive) { $py = $py -replace 'python\.exe$', 'pythonw.exe' }   # 로그온 상태에선 콘솔 창 안 뜨게
foreach ($j in $jobs) {
    $action = New-ScheduledTaskAction -Execute $py -Argument "`"$runner`" $($j.Arg)" -WorkingDirectory $PSScriptRoot
    $trigger = New-ScheduledTaskTrigger -Daily -At $j.At
    $settings = New-ScheduledTaskSettingsSet -WakeToRun -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -ExecutionTimeLimit (New-TimeSpan -Hours $j.Limit) -MultipleInstances IgnoreNew -RestartCount 1 -RestartInterval (New-TimeSpan -Minutes 10)
    Register-ScheduledTask -TaskPath '\ML\' -TaskName $j.Name -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force -ErrorAction Stop | Out-Null
    Write-Host "등록: \ML\$($j.Name) $($j.At) ($($j.Arg))"
}

# 기존 수집 작업은 night 에 포함됐으므로 끔 (삭제 안 함)
if (Get-ScheduledTask -TaskName 'AuctionTenants' -ErrorAction SilentlyContinue) {
    Disable-ScheduledTask -TaskName 'AuctionTenants' | Out-Null; Write-Host '기존 AuctionTenants 끔'
}
Get-ScheduledTask -TaskPath '\ML\' | Format-Table TaskName, State -AutoSize
