param(
    [Parameter(Mandatory = $true)]
    [string] $InputPath,

    [Parameter(Mandatory = $true)]
    [string] $OutputPath
)

$ErrorActionPreference = "Stop"
$toolDir = Join-Path $PSScriptRoot "installed\DicomAnonymizerTool\DicomAnonymizerTool"
$resolvedInput = (Resolve-Path -LiteralPath $InputPath).Path
$resolvedOutput = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($OutputPath)
$resolvedOutputParent = Split-Path -Parent $resolvedOutput

if ($resolvedOutputParent -and -not (Test-Path -LiteralPath $resolvedOutputParent)) {
    New-Item -ItemType Directory -Path $resolvedOutputParent | Out-Null
}

if (-not (Test-Path -LiteralPath (Join-Path $toolDir "DAT.jar"))) {
    throw "RSNA DicomAnonymizerTool is not installed under $toolDir"
}

Push-Location $toolDir
try {
    & java -jar DAT.jar -in $resolvedInput -out $resolvedOutput -da dicom-anonymizer.script -dpa dicom-pixel-anonymizer.script
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        exit $exitCode
    }
    if (-not (Test-Path -LiteralPath $resolvedOutput)) {
        throw "RSNA DAT did not produce expected output: $resolvedOutput"
    }
    exit 0
}
finally {
    Pop-Location
}
