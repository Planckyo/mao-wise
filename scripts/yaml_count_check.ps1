# YAML file count check script
param(
    [Parameter(Mandatory=$true)]
    [string]$PlansDir,
    
    [Parameter(Mandatory=$true)]
    [string]$ExpTasksCsv,
    
    [switch]$ExitOnError
)

try {
    # Check input files
    if (-not (Test-Path $ExpTasksCsv)) {
        Write-Host "ERROR: CSV file not found: $ExpTasksCsv" -ForegroundColor Red
        exit 1
    }
    
    if (-not (Test-Path $PlansDir)) {
        Write-Host "ERROR: Plans directory not found: $PlansDir" -ForegroundColor Red
        exit 1
    }
    
    # Read CSV and count expected records
    $csvContent = Import-Csv $ExpTasksCsv -Encoding UTF8
    $expectedCount = $csvContent.Count
    
    Write-Host "Expected YAML files: $expectedCount" -ForegroundColor Cyan
    
    # Get actual YAML file count
    $yamlFiles = Get-ChildItem $PlansDir -Filter "*.yaml" -ErrorAction SilentlyContinue
    $actualCount = $yamlFiles.Count
    
    Write-Host "Actual YAML files: $actualCount" -ForegroundColor Cyan
    
    # Compare counts
    if ($actualCount -eq $expectedCount) {
        Write-Host "SUCCESS: YAML file count matches! ($actualCount/$expectedCount)" -ForegroundColor Green
        exit 0
    } else {
        Write-Host "ERROR: YAML file count mismatch! Actual $actualCount, Expected $expectedCount" -ForegroundColor Red
        
        # Analyze missing files
        $expectedPlanIds = $csvContent | ForEach-Object { 
            $_.plan_id -replace '[^A-Za-z0-9_\-]', '_'
        }
        $actualPlanIds = $yamlFiles | ForEach-Object { 
            $_.BaseName 
        }
        
        $missingPlanIds = $expectedPlanIds | Where-Object { $_ -notin $actualPlanIds }
        $extraPlanIds = $actualPlanIds | Where-Object { $_ -notin $expectedPlanIds }
        
        if ($missingPlanIds.Count -gt 0) {
            Write-Host "Missing plan_ids:" -ForegroundColor Yellow
            foreach ($missing in $missingPlanIds) {
                Write-Host "  - $missing" -ForegroundColor Yellow
            }
        }
        
        if ($extraPlanIds.Count -gt 0) {
            Write-Host "Extra plan_ids:" -ForegroundColor Yellow
            foreach ($extra in $extraPlanIds) {
                Write-Host "  + $extra" -ForegroundColor Yellow
            }
        }
        
        Write-Host ""
        Write-Host "Repair suggestions:" -ForegroundColor Yellow
        Write-Host "  1. Re-run scripts/repair_pack_plans.py --force" -ForegroundColor Yellow
        Write-Host "  2. Check plan_id format in CSV file" -ForegroundColor Yellow
        Write-Host "  3. Verify directory permissions and disk space" -ForegroundColor Yellow
        
        if ($ExitOnError) {
            exit 1
        } else {
            exit 0
        }
    }
} catch {
    Write-Host "ERROR: Check process failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}