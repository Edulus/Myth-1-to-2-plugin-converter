<#
Bootstraps Python for people who do not have it yet, then starts the studio.

Windows-only. Everything else in this project has zero non-stdlib dependencies
and runs on any OS with Python 3.12+; this script exists only to smooth over
the one real gap for Windows users who have never installed Python before --
the Myth community skews toward exactly that: comfortable with an installer
and a command line, but not necessarily carrying Python already.

Detection deliberately excludes the classic Windows trap: an unconfigured
system often has a fake python.exe under WindowsApps that silently opens the
Microsoft Store instead of running anything. That stub is skipped explicitly,
or this script would report success while doing nothing useful.

If nothing usable is found, this installs Python 3.12 via winget, which ships
by default on any currently supported Windows. If winget is unavailable, it
opens the download page instead and explains what to check during setup.
#>

param(
    [switch]$DetectOnly  # find Python and report, but do not start the studio
)

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

function Get-Python312Command {
    <#
    Returns the command to run Python 3.12+, as an array of exe followed by
    fixed arguments (e.g. @('py','-3.12')), or $null if none was found.
    #>
    $candidates = @()

    if (Get-Command py -ErrorAction SilentlyContinue) {
        $candidates += , @('py', '-3.12')
        $candidates += , @('py', '-3')
    }
    foreach ($name in @('python', 'python3')) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        # The WindowsApps alias stub exists even with no real Python installed
        # and, if run, just pops open the Microsoft Store -- not a Python.
        if ($cmd -and $cmd.Source -notmatch 'WindowsApps') {
            $candidates += , @($name)
        }
    }

    foreach ($candidate in $candidates) {
        $exe = $candidate[0]
        $baseArgs = @()
        if ($candidate.Length -gt 1) { $baseArgs = $candidate[1..($candidate.Length - 1)] }

        $output = & $exe @baseArgs --version
        $line = ($output -join "`n")
        if ($line -match 'Python (\d+)\.(\d+)') {
            $major = [int]$Matches[1]
            $minor = [int]$Matches[2]
            if (($major -gt 3) -or ($major -eq 3 -and $minor -ge 12)) {
                Write-Host "Found $line via '$($candidate -join ' ')'" -ForegroundColor Green
                return $candidate
            }
        }
    }
    return $null
}

function Install-Python {
    <#
    Installs Python 3.12 via winget, if winget is available. Deliberately does
    not try to make the new install usable in THIS console session -- winget
    updates the machine/user PATH and the py launcher's registry entries, but
    a console that is already open does not pick that up. Asking the user to
    run the launcher again is more reliable than guessing install paths.
    #>
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $winget) {
        Write-Host "winget is not available on this system." -ForegroundColor Yellow
        Write-Host "Install Python yourself: https://www.python.org/downloads/"
        Write-Host "When the installer asks, check 'Add python.exe to PATH'."
        Start-Process 'https://www.python.org/downloads/'
        return
    }

    Write-Host "Installing Python 3.12 via winget. This can take a minute or two..." -ForegroundColor Cyan
    winget install --id Python.Python.3.12 -e --source winget `
        --accept-source-agreements --accept-package-agreements
    if ($LASTEXITCODE -eq 0) {
        Write-Host ""
        Write-Host "Python installed. Run launch.bat again to continue." -ForegroundColor Green
        return
    }

    Write-Host "winget could not install Python automatically." -ForegroundColor Yellow
    Write-Host "Install it yourself: https://www.python.org/downloads/"
    Write-Host "When the installer asks, check 'Add python.exe to PATH'."
    Start-Process 'https://www.python.org/downloads/'
}

Write-Host "Myth plugin converter" -ForegroundColor Cyan
Write-Host "Looking for Python 3.12 or newer..."

$python = Get-Python312Command
if (-not $python) {
    Write-Host "Python 3.12+ was not found." -ForegroundColor Yellow
    Install-Python
    exit 1
}

if ($DetectOnly) {
    exit 0
}

$exe = $python[0]
$baseArgs = @()
if ($python.Length -gt 1) { $baseArgs = $python[1..($python.Length - 1)] }

Write-Host "Starting the studio..."
& $exe @baseArgs -m src studio
exit $LASTEXITCODE
