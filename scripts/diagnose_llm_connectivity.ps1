# scripts/diagnose_llm_connectivity.ps1
# LLM Connectivity Diagnostic and Auto-Fix Script

param(
    [switch]$AutoFix = $false,
    [switch]$ForceLocal = $false
)

function Write-Step { param([string]$Message); Write-Host "`nStep: $Message" -ForegroundColor Yellow }
function Write-Success { param([string]$Message); Write-Host "SUCCESS: $Message" -ForegroundColor Green }
function Write-Warning { param([string]$Message); Write-Host "WARNING: $Message" -ForegroundColor Yellow }
function Write-Error { param([string]$Message); Write-Host "ERROR: $Message" -ForegroundColor Red }
function Write-Info { param([string]$Message); Write-Host "INFO: $Message" -ForegroundColor Cyan }

# Setup output file
$timestamp = Get-Date -Format "yyyyMMdd_HHmm"
$outputFile = "reports/diag_llm_$timestamp.txt"
$reportsDir = "reports"
if (-not (Test-Path $reportsDir)) {
    New-Item -ItemType Directory -Path $reportsDir -Force | Out-Null
}

# Start diagnostic
Write-Host "MAO-Wise LLM Connectivity Diagnostic and Auto-Fix" -ForegroundColor Cyan
Write-Host "====================================================" -ForegroundColor Cyan

# Redirect output to file
Start-Transcript -Path $outputFile -Append

Write-Host "Diagnostic start time: $(Get-Date)" -ForegroundColor Gray
Write-Host "====================================================" -ForegroundColor Gray

# 1. Check .env and environment variables
Write-Step "1. Check Environment Configuration"
Write-Host "Checking .env file..." -ForegroundColor Gray
if (Test-Path ".env") {
    Write-Success ".env file exists"
    $envContent = Get-Content ".env" | Where-Object { $_ -match "^(LLM_PROVIDER|OPENAI_API_KEY|AZURE_OPENAI_API_KEY|AZURE_OPENAI_ENDPOINT)" }
    foreach ($line in $envContent) {
        if ($line -match "OPENAI_API_KEY") {
            $maskedKey = $line -replace "=.*", "=***[MASKED]***"
            Write-Host "  $maskedKey" -ForegroundColor Gray
        } else {
            Write-Host "  $line" -ForegroundColor Gray
        }
    }
} else {
    Write-Warning ".env file not found"
}

Write-Host "Checking environment variables..." -ForegroundColor Gray
$llmProvider = $env:LLM_PROVIDER
$openaiKey = $env:OPENAI_API_KEY
$azureKey = $env:AZURE_OPENAI_API_KEY

Write-Host "  LLM_PROVIDER: $(if ($llmProvider) { $llmProvider } else { 'Not Set' })" -ForegroundColor Gray
Write-Host "  OPENAI_API_KEY: $(if ($openaiKey) { 'Set' } else { 'Not Set' })" -ForegroundColor Gray
Write-Host "  AZURE_OPENAI_API_KEY: $(if ($azureKey) { 'Set' } else { 'Not Set' })" -ForegroundColor Gray

# 2. Network connectivity test
Write-Step "2. Network Connectivity Test"

# DNS resolution test
Write-Host "Testing DNS resolution..." -ForegroundColor Gray
try {
    $dnsResult = nslookup api.openai.com 2>$null
    if ($dnsResult -match "Address:") {
        Write-Success "DNS resolution successful: api.openai.com"
        $dnsResult | Where-Object { $_ -match "Address:" } | ForEach-Object { Write-Host "  $_" -ForegroundColor Gray }
    } else {
        Write-Error "DNS resolution failed: api.openai.com"
    }
} catch {
    Write-Error "DNS test exception: $($_.Exception.Message)"
}

# HTTP connection test
Write-Host "Testing HTTP connection..." -ForegroundColor Gray
if ($openaiKey) {
    try {
        $headers = @{
            "Authorization" = "Bearer $openaiKey"
            "Content-Type" = "application/json"
        }
        $response = Invoke-WebRequest -Uri "https://api.openai.com/v1/models" -Headers $headers -TimeoutSec 10 -ErrorAction Stop
        if ($response.StatusCode -eq 200) {
            Write-Success "OpenAI API connection successful (Status: $($response.StatusCode))"
        } else {
            Write-Warning "OpenAI API response abnormal (Status: $($response.StatusCode))"
        }
    } catch {
        Write-Error "OpenAI API connection failed: $($_.Exception.Message)"
    }
} else {
    Write-Warning "Skipping OpenAI API test (API Key not set)"
}

# 3. Certificate chain check
Write-Step "3. Certificate Chain Check"
try {
    $certResult = python -c "import certifi; import ssl; print(f'certifi.where(): {certifi.where()}'); print(f'ssl.OPENSSL_VERSION: {ssl.OPENSSL_VERSION}')" 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Success "Certificate check successful"
        $certResult -split "`n" | ForEach-Object { Write-Host "  $_" -ForegroundColor Gray }
    } else {
        Write-Error "Certificate check failed"
    }
} catch {
    Write-Error "Certificate check exception: $($_.Exception.Message)"
}

# 4. Proxy settings check
Write-Step "4. Proxy Settings Check"
$httpsProxy = $env:HTTPS_PROXY
$allProxy = $env:ALL_PROXY
$httpProxy = $env:HTTP_PROXY

Write-Host "Proxy settings:" -ForegroundColor Gray
Write-Host "  HTTPS_PROXY: $(if ($httpsProxy) { $httpsProxy } else { 'Not Set' })" -ForegroundColor Gray
Write-Host "  ALL_PROXY: $(if ($allProxy) { $allProxy } else { 'Not Set' })" -ForegroundColor Gray
Write-Host "  HTTP_PROXY: $(if ($httpProxy) { $httpProxy } else { 'Not Set' })" -ForegroundColor Gray

# 5. Diagnostic results summary
Write-Step "5. Diagnostic Results Summary"
$diagnosisResults = @()

# Check key issues
$hasOpenAIKey = [bool]$openaiKey
$hasAzureKey = [bool]$azureKey
$hasProvider = [bool]$llmProvider

if (-not $hasOpenAIKey -and -not $hasAzureKey) {
    $diagnosisResults += "ERROR: No LLM API Key set"
} elseif ($hasOpenAIKey -and -not $hasProvider) {
    $diagnosisResults += "WARNING: OpenAI Key set but LLM_PROVIDER not specified"
} elseif ($hasProvider -and $llmProvider -eq "openai" -and -not $hasOpenAIKey) {
    $diagnosisResults += "ERROR: LLM_PROVIDER=openai but OPENAI_API_KEY not set"
} elseif ($hasProvider -and $llmProvider -eq "azure" -and -not $hasAzureKey) {
    $diagnosisResults += "ERROR: LLM_PROVIDER=azure but AZURE_OPENAI_API_KEY not set"
} else {
    $diagnosisResults += "SUCCESS: Environment configuration check passed"
}

# 6. Auto-fix logic
if ($AutoFix -or $ForceLocal) {
    Write-Step "6. Auto-Fix"
    
    if ($ForceLocal) {
        Write-Info "Force switching to local mode"
        $env:LLM_PROVIDER = "local"
        Write-Success "LLM_PROVIDER set to local"
        
        # Continue with pipeline_local.ps1
        Write-Info "Continuing with pipeline_local.ps1..."
        Write-Host "====================================================" -ForegroundColor Gray
        Stop-Transcript
        
        # Execute local pipeline
        powershell -ExecutionPolicy Bypass -File scripts\pipeline_local.ps1 -UseOCR:$true -DoTrain:$true
        exit 0
    }
    
    # Check if fix needed
    if ($diagnosisResults -contains "ERROR: No LLM API Key set") {
        Write-Info "Detected no API Key set, attempting auto-fix..."
        
        if (-not $hasOpenAIKey -and -not $hasAzureKey) {
            Write-Info "Calling set_llm_keys.ps1 to set credentials..."
            try {
                powershell -ExecutionPolicy Bypass -File scripts\set_llm_keys.ps1
                if ($LASTEXITCODE -eq 0) {
                    Write-Success "Credential setup completed, re-running diagnostic..."
                    Stop-Transcript
                    
                    # Re-run diagnostic
                    powershell -ExecutionPolicy Bypass -File scripts\diagnose_llm_connectivity.ps1 -AutoFix:$true
                    exit 0
                } else {
                    Write-Warning "Credential setup failed, switching to local mode"
                    $env:LLM_PROVIDER = "local"
                    Write-Success "LLM_PROVIDER set to local"
                }
            } catch {
                Write-Error "Credential setup exception: $($_.Exception.Message)"
                Write-Info "Switching to local mode"
                $env:LLM_PROVIDER = "local"
            }
        }
    }
    
    # If OpenAI fails, try Azure
    if ($hasOpenAIKey -and $llmProvider -eq "openai") {
        Write-Info "OpenAI connection failed, trying Azure..."
        try {
            powershell -ExecutionPolicy Bypass -File scripts\set_llm_keys.ps1 -Provider azure
            if ($LASTEXITCODE -eq 0) {
                Write-Success "Azure credentials setup completed, re-running diagnostic..."
                Stop-Transcript
                
                # Re-run diagnostic
                powershell -ExecutionPolicy Bypass -File scripts\diagnose_llm_connectivity.ps1 -AutoFix:$true
                exit 0
            }
        } catch {
            Write-Warning "Azure setup failed, switching to local mode"
            $env:LLM_PROVIDER = "local"
        }
    }
    
    # Final fallback to local mode
    if ($env:LLM_PROVIDER -ne "local") {
        Write-Info "All online modes failed, switching to local mode"
        $env:LLM_PROVIDER = "local"
        Write-Success "LLM_PROVIDER set to local"
        
        # Continue with pipeline_local.ps1
        Write-Info "Continuing with pipeline_local.ps1..."
        Write-Host "====================================================" -ForegroundColor Gray
        Stop-Transcript
        
        # Execute local pipeline
        powershell -ExecutionPolicy Bypass -File scripts\pipeline_local.ps1 -UseOCR:$true -DoTrain:$true
        exit 0
    }
}

# 7. Output diagnostic report
Write-Step "7. Generate Diagnostic Report"
Write-Host "Diagnostic completion time: $(Get-Date)" -ForegroundColor Gray
Write-Host "====================================================" -ForegroundColor Gray

Write-Host "`nDiagnostic Results Summary:" -ForegroundColor Cyan
foreach ($result in $diagnosisResults) {
    Write-Host $result
}

Write-Host "`nDiagnostic report saved to: $outputFile" -ForegroundColor Green

# Stop transcript
Stop-Transcript

# Show last 40 lines of report
Write-Host "`nLast 40 lines of diagnostic report:" -ForegroundColor Cyan
Get-Content $outputFile | Select-Object -Last 40 | ForEach-Object { Write-Host $_ }

# Show current model_status
Write-Host "`nCurrent model_status:" -ForegroundColor Cyan
try {
    $statusResponse = Invoke-WebRequest -Uri "http://localhost:8000/api/maowise/v1/admin/model_status" -TimeoutSec 5 -ErrorAction Stop
    if ($statusResponse.StatusCode -eq 200) {
        $statusData = $statusResponse.Content | ConvertFrom-Json
        Write-Host "  llm_provider: $($statusData.llm_provider)" -ForegroundColor Gray
        Write-Host "  llm_key_source: $($statusData.llm_key_source)" -ForegroundColor Gray
    } else {
        Write-Warning "API service response abnormal (Status: $($statusResponse.StatusCode))"
    }
} catch {
    Write-Warning "Cannot get model_status (API service may not be running)"
}

Write-Host "`n====================================================" -ForegroundColor Cyan
Write-Host "Diagnostic completed!" -ForegroundColor Green
