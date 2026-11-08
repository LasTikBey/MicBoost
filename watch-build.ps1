$ErrorActionPreference = "Stop"
$root = [System.IO.Path]::GetFullPath($PSScriptRoot)
$buildScript = Join-Path $root "build.bat"
$micboostDir = Join-Path $root "micboost"
$assetsDir = Join-Path $root "assets"
$packagingDir = Join-Path $root "packaging"
$testsDir = Join-Path $root "tests"
$docsDir = Join-Path $root "docs"

$watchConfigs = @(
    @{ Name = "root"; Path = $root; Recursive = $false },
    @{ Name = "micboost"; Path = $micboostDir; Recursive = $true },
    @{ Name = "assets"; Path = $assetsDir; Recursive = $true },
    @{ Name = "packaging"; Path = $packagingDir; Recursive = $false },
    @{ Name = "tests"; Path = $testsDir; Recursive = $true },
    @{ Name = "docs"; Path = $docsDir; Recursive = $false }
)

function Test-RelevantPath([string]$fullPath) {
    $path = [System.IO.Path]::GetFullPath($fullPath)
    $name = [System.IO.Path]::GetFileName($path)
    $parent = [System.IO.Path]::GetDirectoryName($path)

    if ($parent -ieq $root) {
        return $name -in @("main.py", "requirements.txt", "requirements-dev.txt", "build.bat")
    }
    if ($path.StartsWith("$micboostDir\", [System.StringComparison]::OrdinalIgnoreCase)) {
        return [System.IO.Path]::GetExtension($path) -ieq ".py"
    }
    if ($path.StartsWith("$assetsDir\", [System.StringComparison]::OrdinalIgnoreCase)) {
        return $true
    }
    if ($parent -ieq $packagingDir) {
        return $name -in @("micboost.spec", "installer.iss", "micboost.ico", "uninstall.bat")
    }
    if ($path.StartsWith("$testsDir\", [System.StringComparison]::OrdinalIgnoreCase)) {
        return [System.IO.Path]::GetExtension($path) -ieq ".py"
    }
    if ($parent -ieq $docsDir) {
        return $name -ieq "KULLANIM_KILAVUZU.md"
    }
    return $false
}

function Test-AppRunning {
    return $null -ne (Get-Process -Name "MicBoost" -ErrorAction SilentlyContinue)
}

function Invoke-Build {
    if (Test-AppRunning) {
        Write-Host "MicBoost is running. Close it to let the watcher build the updated EXE."
        return "deferred"
    }

    Write-Host ""
    Write-Host "=== Changes detected; rebuilding MicBoost ==="
    & $buildScript --no-pause
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Build failed. Fix the reported error and save a relevant file to retry."
        return "failed"
    }
    Write-Host "Build completed. dist\MicBoost.exe has been refreshed."
    return "success"
}

$watchers = @()
$subscriptions = @()
try {
    foreach ($config in $watchConfigs) {
        if (-not (Test-Path -LiteralPath $config.Path -PathType Container)) {
            throw "Watch directory not found: $($config.Path)"
        }
        $watcher = New-Object System.IO.FileSystemWatcher
        $watcher.Path = $config.Path
        $watcher.Filter = "*"
        $watcher.IncludeSubdirectories = $config.Recursive
        $watcher.NotifyFilter = [IO.NotifyFilters]"FileName, DirectoryName, LastWrite"

        foreach ($eventName in @("Changed", "Created", "Deleted", "Renamed", "Error")) {
            $sourceId = "MicBoostBuild.$($config.Name).$eventName"
            Register-ObjectEvent -InputObject $watcher -EventName $eventName `
                -SourceIdentifier $sourceId | Out-Null
            $subscriptions += $sourceId
        }
        $watcher.EnableRaisingEvents = $true
        $watchers += $watcher
    }

    Write-Host "Watching MicBoost sources. Press Ctrl+C to stop."
    $waitingForAppClose = $false
    $initialState = Invoke-Build
    if ($initialState -eq "deferred") {
        $waitingForAppClose = $true
    }

    $pendingBuild = $false
    $lastRelevantChange = [DateTime]::UtcNow
    while ($true) {
        $event = Wait-Event -Timeout 1
        if ($null -ne $event) {
            if ($event.SourceIdentifier.EndsWith(".Error")) {
                $exception = $event.SourceEventArgs.GetException()
                Remove-Event -EventIdentifier $event.EventIdentifier
                throw "File watcher failed: $exception"
            }

            $changedPath = $event.SourceEventArgs.FullPath
            if (Test-RelevantPath $changedPath) {
                Write-Host "Change detected: $changedPath"
                $pendingBuild = $true
                $waitingForAppClose = $false
                $lastRelevantChange = [DateTime]::UtcNow
            }
            Remove-Event -EventIdentifier $event.EventIdentifier
        }

        if ($pendingBuild -and ([DateTime]::UtcNow - $lastRelevantChange).TotalSeconds -ge 1.5) {
            $pendingBuild = $false
            $state = Invoke-Build
            if ($state -eq "deferred") {
                $waitingForAppClose = $true
            }
        }

        if ($waitingForAppClose -and -not (Test-AppRunning)) {
            $waitingForAppClose = $false
            $state = Invoke-Build
            if ($state -eq "deferred") {
                $waitingForAppClose = $true
            }
        }
    }
}
finally {
    foreach ($watcher in $watchers) {
        $watcher.EnableRaisingEvents = $false
        $watcher.Dispose()
    }
    foreach ($sourceId in $subscriptions) {
        Unregister-Event -SourceIdentifier $sourceId -ErrorAction SilentlyContinue
    }
}
