# Notification hook: compaction_save.ps1
#
# Fires on Notification:PreCompact — just before Claude Code summarises the
# context window. Appends a timestamped compaction marker to task_state.md so
# the session history is recoverable.
#
# IMPORTANT: Notification hooks receive data via ENVIRONMENT VARIABLES, not
# stdin. Do NOT read stdin in a Notification hook — it will hang.
#
# Wire in .claude/settings.json:
#   "Notification": [{ "matcher": "PreCompact", "hooks": [{ "type": "command",
#     "command": "pwsh -NonInteractive -File C:\\...\\compaction_save.ps1" }] }]
#
# Exit 0 always — this hook observes, it does not block.

$eventType = $env:CLAUDE_NOTIFICATION_TYPE

if ($eventType -ne "PreCompact") {
    exit 0
}

$stateFile = Join-Path $PSScriptRoot ".." "task_state.md"

if (-not (Test-Path $stateFile)) {
    @'
# Task State

<!-- This file is maintained by Claude during the session.
     The compaction_save.ps1 hook appends a marker whenever the context
     is compacted. Read this file at the start of a new session to resume. -->

## Current task
(not yet written — Claude should update this as work progresses)

## Done
(none yet)

## Next step
(not yet written)

## Blockers / open decisions
(none)
'@ | Set-Content -Path $stateFile -Encoding UTF8
}

$timestamp = (Get-Date).ToUniversalTime().ToString("yyyy-MM-dd HH:mm UTC")

@"

---
## Compaction checkpoint: $timestamp
Context was summarised at this point.
State above is the last checkpoint before compaction.
"@ | Add-Content -Path $stateFile -Encoding UTF8

exit 0
