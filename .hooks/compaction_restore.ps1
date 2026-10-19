# compaction_restore.ps1
#
# Reads task_state.md and prints its content so Claude can resume from where
# the previous session left off.
#
# This is NOT a hook — run it manually at the start of a session, or instruct
# Claude to run it:
#   "At the start of every session, run: pwsh .hooks/compaction_restore.ps1"
#
# Usage:
#   pwsh .hooks/compaction_restore.ps1
#   pwsh .hooks/compaction_restore.ps1 path/to/task_state.md

param(
    [string]$StatePath = "task_state.md"
)

Write-Host "========================================"
Write-Host "  SESSION RESUME — reading task_state.md"
Write-Host "========================================"
Write-Host ""

if (-not (Test-Path $StatePath)) {
    Write-Host "No task_state.md found at: $StatePath"
    Write-Host ""
    Write-Host "Start a new one with the template at .hooks/task_state.md.template"
    exit 0
}

Get-Content $StatePath -Encoding UTF8 | Write-Host

Write-Host ""
Write-Host "========================================"
Write-Host "  End of task_state.md"
Write-Host "  Review the above and continue the task."
Write-Host "========================================"
