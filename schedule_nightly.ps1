# schedule_nightly.ps1
# Windows タスクスケジューラに毎日 02:00 実行のタスクを登録する
# 使い方: PowerShell を「管理者として実行」してからこのスクリプトを実行
#   .\schedule_nightly.ps1
# 削除したいとき:
#   Unregister-ScheduledTask -TaskName "NRC_Pipeline_Nightly" -Confirm:$false

$taskName   = "NRC_Pipeline_Nightly"
$projectDir = "c:\Users\harut\Downloads\就活\Python_ポートフォリオ\ランニング結果管理システム"
$python     = "$projectDir\.venv\Scripts\python.exe"
$script     = "$projectDir\run_pipeline.py"

$action   = New-ScheduledTaskAction `
    -Execute        $python `
    -Argument       $script `
    -WorkingDirectory $projectDir

$trigger  = New-ScheduledTaskTrigger -Daily -At "02:00"

$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 60) `
    -StartWhenAvailable `       # 万一PCがスリープ中でも起動後に実行
    -WakeToRun $false           # スリープ解除はしない（省エネ優先）

Register-ScheduledTask `
    -TaskName $taskName `
    -Action   $action `
    -Trigger  $trigger `
    -Settings $settings `
    -RunLevel Highest `
    -Force | Out-Null

Write-Host ""
Write-Host "タスク '$taskName' を登録しました" -ForegroundColor Green
Write-Host "  実行時刻 : 毎日 02:00"
Write-Host "  ログ出力 : $projectDir\pipeline.log"
Write-Host ""
Write-Host "手動で即時実行したい場合:"
Write-Host "  Start-ScheduledTask -TaskName '$taskName'"
