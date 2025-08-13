#!/usr/bin/env pwsh
# MAO-Wise LLM API Keys Configuration Script
# Secure management of API keys with interactive input, environment variables, and connectivity testing

param(
    [Parameter()]
    [ValidateSet("openai", "azure")]
    [string]$Provider = "openai",
    
    [Parameter()]
    [string]$OpenAIKey,
    
    [Parameter()]
    [string]$AzureKey,
    
    [Parameter()]
    [string]$AzureEndpoint,
    
    [Parameter()]
    [string]$AzureDeployment,
    
    [Parameter()]
    [ValidateSet("process", "user")]
    [string]$Scope = "process",
    
    [Parameter()]
    [bool]$PersistToEnv = $true,
    
    [Parameter()]
    [switch]$Unset
)

# Set encoding and error handling
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::UTF8
$ErrorActionPreference = "Stop"

# Color output functions
function Write-ColorOutput {
    param([string]$Message, [string]$Color = "White")
    Write-Host $Message -ForegroundColor $Color
}

function Write-Step { param([string]$Message); Write-ColorOutput "[INFO] $Message" "Cyan" }
function Write-Success { param([string]$Message); Write-ColorOutput "[OK] $Message" "Green" }
function Write-Warning { param([string]$Message); Write-ColorOutput "[WARN] $Message" "Yellow" }
function Write-Error { param([string]$Message); Write-ColorOutput "[ERROR] $Message" "Red" }

# Utility functions
function Get-RepoRoot {
    $currentDir = Get-Location
    $gitDir = Join-Path $currentDir ".git"
    if (Test-Path $gitDir) {
        return $currentDir
    }
    
    # Search upwards for .git directory
    $parent = Split-Path $currentDir -Parent
    while ($parent -and (Split-Path $parent -Parent)) {
        $gitDir = Join-Path $parent ".git"
        if (Test-Path $gitDir) {
            return $parent
        }
        $parent = Split-Path $parent -Parent
    }
    
    # Fallback to current directory
    return $currentDir
}

function ConvertFrom-SecureString-PlainText {
    param([SecureString]$SecureString)
    
    try {
        $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureString)
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
    } finally {
        if ($ptr) {
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
        }
    }
}

function Get-MaskedKey {
    param([string]$Key)
    
    if (-not $Key -or $Key.Length -lt 8) {
        return "[EMPTY]"
    }
    
    $prefix = $Key.Substring(0, [Math]::Min(4, $Key.Length))
    $suffix = $Key.Substring([Math]::Max(0, $Key.Length - 4))
    $masked = "*" * [Math]::Max(0, $Key.Length - 8)
    
    return "$prefix$masked$suffix"
}

function Ensure-GitIgnore {
    Write-Step "Ensuring .gitignore contains necessary entries..."
    
    $repoRoot = Get-RepoRoot
    $gitignoreFile = Join-Path $repoRoot ".gitignore"
    
    $requiredEntries = @(
        ".env",
        ".env.local", 
        "datasets/cache/"
    )
    
    $existingContent = @()
    if (Test-Path $gitignoreFile) {
        $existingContent = Get-Content $gitignoreFile -Encoding UTF8
    }
    
    $entriesToAdd = @()
    foreach ($entry in $requiredEntries) {
        $found = $false
        foreach ($line in $existingContent) {
            if ($line.Trim() -eq $entry.Trim()) {
                $found = $true
                break
            }
        }
        if (-not $found) {
            $entriesToAdd += $entry
        }
    }
    
    if ($entriesToAdd.Count -gt 0) {
        Write-Step "Adding missing entries to .gitignore: $($entriesToAdd -join ', ')"
        
        $newContent = $existingContent + "" + "# MAO-Wise sensitive files" + $entriesToAdd
        Set-Content -Path $gitignoreFile -Value $newContent -Encoding UTF8
        
        Write-Success ".gitignore updated with $($entriesToAdd.Count) new entries"
    } else {
        Write-Success ".gitignore already contains all required entries"
    }
}

function Get-SecureInput {
    param(
        [string]$Prompt,
        [string]$ConfirmPrompt = $null
    )
    
    Write-Host "$Prompt (input will be hidden): " -NoNewline -ForegroundColor Yellow
    $secureInput = Read-Host -AsSecureString
    
    if ($ConfirmPrompt) {
        Write-Host "$ConfirmPrompt (input will be hidden): " -NoNewline -ForegroundColor Yellow
        $secureConfirm = Read-Host -AsSecureString
        
        $input1 = ConvertFrom-SecureString-PlainText $secureInput
        $input2 = ConvertFrom-SecureString-PlainText $secureConfirm
        
        if ($input1 -ne $input2) {
            Write-Error "Inputs do not match. Please try again."
            return $null
        }
    }
    
    return ConvertFrom-SecureString-PlainText $secureInput
}

function Update-EnvFile {
    param(
        [hashtable]$Variables
    )
    
    if (-not $PersistToEnv) {
        return
    }
    
    Write-Step "Updating .env file..."
    
    $repoRoot = Get-RepoRoot
    $envFile = Join-Path $repoRoot ".env"
    
    $existingLines = @()
    if (Test-Path $envFile) {
        $existingLines = Get-Content $envFile -Encoding UTF8
    }
    
    # Keys to manage
    $managedKeys = @(
        "OPENAI_API_KEY",
        "LLM_PROVIDER", 
        "AZURE_OPENAI_API_KEY",
        "AZURE_OPENAI_ENDPOINT",
        "AZURE_OPENAI_DEPLOYMENT"
    )
    
    # Filter out managed keys from existing content
    $filteredLines = @()
    foreach ($line in $existingLines) {
        $shouldKeep = $true
        foreach ($key in $managedKeys) {
            if ($line.StartsWith("$key=")) {
                $shouldKeep = $false
                break
            }
        }
        if ($shouldKeep) {
            $filteredLines += $line
        }
    }
    
    # Add new variables
    $newLines = $filteredLines
    foreach ($key in $Variables.Keys) {
        $value = $Variables[$key]
        if ($value) {
            $newLines += "$key=$value"
        }
    }
    
    # Write to file with UTF-8 encoding
    Set-Content -Path $envFile -Value $newLines -Encoding UTF8
    
    Write-Success ".env file updated at: $envFile"
}

function Set-EnvironmentVariables {
    param(
        [hashtable]$Variables
    )
    
    Write-Step "Setting environment variables (scope: $Scope)..."
    
    foreach ($key in $Variables.Keys) {
        $value = $Variables[$key]
        
        # Set for current session
        Set-Item -Path "env:$key" -Value $value
        
        # Set for user scope if requested
        if ($Scope -eq "user") {
            [Environment]::SetEnvironmentVariable($key, $value, "User")
        }
    }
    
    Write-Success "Environment variables set for current session"
    if ($Scope -eq "user") {
        Write-Success "Environment variables set for user scope (persistent)"
    }
}

function Remove-EnvironmentVariables {
    param(
        [string[]]$Keys
    )
    
    Write-Step "Removing environment variables..."
    
    foreach ($key in $Keys) {
        # Remove from current session
        if (Test-Path "env:$key") {
            Remove-Item -Path "env:$key"
        }
        
        # Remove from user scope
        [Environment]::SetEnvironmentVariable($key, $null, "User")
    }
    
    Write-Success "Environment variables removed"
}

function Remove-FromEnvFile {
    param(
        [string[]]$Keys
    )
    
    if (-not $PersistToEnv) {
        return
    }
    
    Write-Step "Removing keys from .env file..."
    
    $repoRoot = Get-RepoRoot
    $envFile = Join-Path $repoRoot ".env"
    
    if (-not (Test-Path $envFile)) {
        Write-Warning ".env file does not exist"
        return
    }
    
    $existingLines = Get-Content $envFile -Encoding UTF8
    $filteredLines = @()
    
    foreach ($line in $existingLines) {
        $shouldKeep = $true
        foreach ($key in $Keys) {
            if ($line.StartsWith("$key=")) {
                $shouldKeep = $false
                break
            }
        }
        if ($shouldKeep) {
            $filteredLines += $line
        }
    }
    
    Set-Content -Path $envFile -Value $filteredLines -Encoding UTF8
    
    Write-Success "Keys removed from .env file"
}

function Test-Connectivity {
    Write-Step "Testing LLM connectivity..."
    
    $repoRoot = Get-RepoRoot
    $testScript = Join-Path $repoRoot "scripts/test_llm_connectivity.py"
    
    if (-not (Test-Path $testScript)) {
        Write-Warning "Connectivity test script not found: $testScript"
        return
    }
    
    try {
        Write-Host "Running connectivity test..." -ForegroundColor Gray
        
        # 设置PYTHONPATH为项目根目录
        $env:PYTHONPATH = $repoRoot
        
        # 使用 python -X dev 运行测试并捕获完整输出
        $result = & python -X dev $testScript 2>&1
        $exitCode = $LASTEXITCODE
        
        # 对输出进行安全脱敏（掩码API Key）
        $sanitizedResult = $result | ForEach-Object {
            $line = $_.ToString()
            # 掩码 sk- 开头的密钥
            $line = $line -replace 'sk-[a-zA-Z0-9]{20,}', 'sk-****[MASKED]****'
            # 掩码其他可能的密钥格式
            $line = $line -replace '[a-f0-9]{32}', '****[MASKED]****'
            return $line
        }
        
        if ($exitCode -eq 0) {
            Write-Success "Connectivity test completed successfully"
            Write-Host $sanitizedResult -ForegroundColor Gray
        } else {
            Write-Warning "Connectivity test failed (exit code: $exitCode)"
            Write-Host "Complete traceback:" -ForegroundColor Red
            Write-Host $sanitizedResult -ForegroundColor Red
            
            Write-Host "`nTroubleshooting suggestions:" -ForegroundColor Yellow
            Write-Host "1. Check your internet connection" -ForegroundColor Gray
            Write-Host "2. Verify API key is valid and has quota" -ForegroundColor Gray
            Write-Host "3. Check if corporate proxy/firewall blocks OpenAI" -ForegroundColor Gray
            Write-Host "4. Ensure API key format is correct (starts with 'sk-')" -ForegroundColor Gray
            Write-Host "5. Install required packages: pip install openai tiktoken" -ForegroundColor Gray
        }
        
    } catch {
        Write-Warning "Failed to run connectivity test: $($_.Exception.Message)"
        Write-Host "Full exception details:" -ForegroundColor Red
        Write-Host $_.ScriptStackTrace -ForegroundColor Red
    }
}

function Show-Configuration {
    param(
        [hashtable]$Variables
    )
    
    Write-Step "Current configuration:"
    
    foreach ($key in $Variables.Keys) {
        $value = $Variables[$key]
        if ($value) {
            $masked = Get-MaskedKey $value
            Write-Host "  $key = $masked" -ForegroundColor Gray
        }
    }
    
    Write-Host "  Scope: $Scope" -ForegroundColor Gray
    Write-Host "  Persist to .env: $PersistToEnv" -ForegroundColor Gray
}

# Main execution
function Main {
    Write-ColorOutput "MAO-Wise LLM API Keys Configuration" "Magenta"
    Write-Host "================================================" -ForegroundColor Magenta
    
    try {
        # Ensure .gitignore is properly configured
        Ensure-GitIgnore
        
        if ($Unset) {
            Write-Step "Removing API keys..."
            
            $keysToRemove = @(
                "OPENAI_API_KEY",
                "LLM_PROVIDER",
                "AZURE_OPENAI_API_KEY", 
                "AZURE_OPENAI_ENDPOINT",
                "AZURE_OPENAI_DEPLOYMENT"
            )
            
            Remove-EnvironmentVariables -Keys $keysToRemove
            Remove-FromEnvFile -Keys $keysToRemove
            
            Write-Success "API keys have been removed"
            return
        }
        
        $variables = @{}
        
        # Handle OpenAI provider
        if ($Provider -eq "openai") {
            if (-not $OpenAIKey) {
                Write-Host "`nOpenAI API Key is required for this provider." -ForegroundColor Yellow
                $OpenAIKey = Get-SecureInput -Prompt "Enter your OpenAI API Key"
                
                if (-not $OpenAIKey) {
                    Write-Error "OpenAI API Key is required"
                    return
                }
            }
            
            # Validate OpenAI key format
            if (-not $OpenAIKey.StartsWith("sk-")) {
                Write-Warning "OpenAI API Key should start with 'sk-'"
            }
            
            $variables["OPENAI_API_KEY"] = $OpenAIKey
            $variables["LLM_PROVIDER"] = "openai"
        }
        
        # Handle Azure provider
        elseif ($Provider -eq "azure") {
            if (-not $AzureKey) {
                Write-Host "`nAzure OpenAI API Key is required for this provider." -ForegroundColor Yellow
                $AzureKey = Get-SecureInput -Prompt "Enter your Azure OpenAI API Key"
            }
            
            if (-not $AzureEndpoint) {
                Write-Host "Enter your Azure OpenAI Endpoint: " -NoNewline -ForegroundColor Yellow
                $AzureEndpoint = Read-Host
            }
            
            if (-not $AzureDeployment) {
                Write-Host "Enter your Azure OpenAI Deployment name: " -NoNewline -ForegroundColor Yellow
                $AzureDeployment = Read-Host
            }
            
            if (-not $AzureKey -or -not $AzureEndpoint -or -not $AzureDeployment) {
                Write-Error "Azure provider requires API key, endpoint, and deployment name"
                return
            }
            
            $variables["AZURE_OPENAI_API_KEY"] = $AzureKey
            $variables["AZURE_OPENAI_ENDPOINT"] = $AzureEndpoint
            $variables["AZURE_OPENAI_DEPLOYMENT"] = $AzureDeployment
            $variables["LLM_PROVIDER"] = "azure"
        }
        
        # Show configuration (with masked keys)
        Show-Configuration -Variables $variables
        
        # Update environment variables
        Set-EnvironmentVariables -Variables $variables
        
        # Update .env file
        Update-EnvFile -Variables $variables
        
        Write-Success "API keys configured successfully!"
        
        # Test connectivity for OpenAI
        if ($Provider -eq "openai") {
            Test-Connectivity
        }
        
    } catch {
        Write-Error "Configuration failed: $($_.Exception.Message)"
        Write-Host $_.ScriptStackTrace -ForegroundColor Red
        exit 1
    }
}

# Script entry point
if ($MyInvocation.InvocationName -ne '.') {
    Main
}
