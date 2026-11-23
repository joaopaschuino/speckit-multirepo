# Delegate to the project's core check-prerequisites.ps1 (see scripts/bash/check-prerequisites.sh).
$core = Join-Path $PSScriptRoot '..\..\..\..\scripts\powershell\check-prerequisites.ps1'
if (-not (Test-Path $core)) {
    Write-Error "multi-repo: Spec Kit's core check-prerequisites.ps1 not found at .specify/scripts/powershell/ (run specify init)"
    exit 1
}
& $core @args
exit $LASTEXITCODE
