# PostToolUse hook: test_gate.ps1
#
# Fires after a Bash/PowerShell tool call that contains "git commit".
# Runs pytest and signals failure if tests are broken.
#
# NOTE: PostToolUse fires AFTER the tool has already run. Exit 2 cannot undo
# the commit — it stops the agent loop so Claude doesn't keep building on a
# broken state. For a true pre-commit gate, move to PreToolUse.
#
# Wire in .claude/settings.json:
#   "PostToolUse": [{ "matcher": "Bash|PowerShell", "hooks": [{ "type": "command",
#     "command": "pwsh -NonInteractive -File C:\\...\\test_gate.ps1",
#     "timeout": 60 }] }]
#
# Exit 0: tests pass (or hook does not apply) — agent continues
# Exit 2: tests failing — agent loop stops, failures shown

$raw = [Console]::In.ReadToEnd()

if (-not $raw) { exit 0 }

try {
    $data = $raw | ConvertFrom-Json
} catch {
    exit 0
}

$toolName = $data.tool_name
$cmd = $data.tool_input.command

# Only act on Bash or PowerShell tool calls.
if ($toolName -notin @("Bash", "PowerShell")) { exit 0 }

# Only act on git commit commands.
if ($cmd -notmatch "git commit") { exit 0 }

# Run the test suite.
$result = & python -m pytest tests/ -q 2>&1
$exitCode = $LASTEXITCODE

if ($exitCode -ne 0) {
    Write-Host "Tests failing after commit."
    Write-Host ""
    Write-Host ($result -join "`n")
    Write-Host ""
    Write-Host "Fix the failing tests before continuing. The commit exists but the"
    Write-Host "agent loop has been stopped to prevent further broken changes."
    exit 2
}

exit 0
