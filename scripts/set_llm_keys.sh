#!/bin/bash
# MAO-Wise LLM API Keys Configuration Script (Linux/Mac)
# Secure management of API keys with interactive input, environment variables, and connectivity testing

set -euo pipefail

# Default values
PROVIDER="openai"
OPENAI_KEY=""
AZURE_KEY=""
AZURE_ENDPOINT=""
AZURE_DEPLOYMENT=""
SCOPE="process"
PERSIST_TO_ENV=true
UNSET=false

# Color output functions
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
GRAY='\033[0;37m'
NC='\033[0m' # No Color

log_step() { echo -e "${CYAN}[INFO] $1${NC}"; }
log_success() { echo -e "${GREEN}[OK] $1${NC}"; }
log_warning() { echo -e "${YELLOW}[WARN] $1${NC}"; }
log_error() { echo -e "${RED}[ERROR] $1${NC}"; }

# Usage function
usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -p, --provider PROVIDER     Provider: openai|azure (default: openai)"
    echo "  -k, --openai-key KEY        OpenAI API Key"
    echo "  -a, --azure-key KEY         Azure OpenAI API Key"
    echo "  -e, --azure-endpoint URL    Azure OpenAI Endpoint"
    echo "  -d, --azure-deployment NAME Azure OpenAI Deployment"
    echo "  -s, --scope SCOPE           Scope: process|user (default: process)"
    echo "  --no-persist               Don't persist to .env file"
    echo "  --unset                    Remove all API keys"
    echo "  -h, --help                 Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 --provider openai                    # Interactive OpenAI setup"
    echo "  $0 --provider openai --openai-key sk-... --scope user"
    echo "  $0 --unset                              # Remove all keys"
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -p|--provider)
            PROVIDER="$2"
            shift 2
            ;;
        -k|--openai-key)
            OPENAI_KEY="$2"
            shift 2
            ;;
        -a|--azure-key)
            AZURE_KEY="$2"
            shift 2
            ;;
        -e|--azure-endpoint)
            AZURE_ENDPOINT="$2"
            shift 2
            ;;
        -d|--azure-deployment)
            AZURE_DEPLOYMENT="$2"
            shift 2
            ;;
        -s|--scope)
            SCOPE="$2"
            shift 2
            ;;
        --no-persist)
            PERSIST_TO_ENV=false
            shift
            ;;
        --unset)
            UNSET=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            usage
            exit 1
            ;;
    esac
done

# Utility functions
get_repo_root() {
    local current_dir="$(pwd)"
    
    # Search upwards for .git directory
    while [[ "$current_dir" != "/" ]]; do
        if [[ -d "$current_dir/.git" ]]; then
            echo "$current_dir"
            return
        fi
        current_dir="$(dirname "$current_dir")"
    done
    
    # Fallback to current directory
    pwd
}

get_masked_key() {
    local key="$1"
    
    if [[ -z "$key" || ${#key} -lt 8 ]]; then
        echo "[EMPTY]"
        return
    fi
    
    local prefix="${key:0:4}"
    local suffix="${key: -4}"
    local masked_length=$((${#key} - 8))
    local masked=$(printf '%*s' "$masked_length" | tr ' ' '*')
    
    echo "${prefix}${masked}${suffix}"
}

ensure_gitignore() {
    log_step "Ensuring .gitignore contains necessary entries..."
    
    local repo_root
    repo_root=$(get_repo_root)
    local gitignore_file="$repo_root/.gitignore"
    
    local required_entries=(".env" ".env.local" "datasets/cache/")
    local entries_to_add=()
    
    # Check existing entries
    for entry in "${required_entries[@]}"; do
        if [[ ! -f "$gitignore_file" ]] || ! grep -Fxq "$entry" "$gitignore_file"; then
            entries_to_add+=("$entry")
        fi
    done
    
    if [[ ${#entries_to_add[@]} -gt 0 ]]; then
        log_step "Adding missing entries to .gitignore: ${entries_to_add[*]}"
        
        {
            if [[ -f "$gitignore_file" ]]; then
                cat "$gitignore_file"
            fi
            echo ""
            echo "# MAO-Wise sensitive files"
            printf '%s\n' "${entries_to_add[@]}"
        } > "$gitignore_file.tmp" && mv "$gitignore_file.tmp" "$gitignore_file"
        
        log_success ".gitignore updated with ${#entries_to_add[@]} new entries"
    else
        log_success ".gitignore already contains all required entries"
    fi
}

get_secure_input() {
    local prompt="$1"
    local value
    
    echo -n -e "${YELLOW}$prompt (input will be hidden): ${NC}"
    read -s value
    echo
    
    echo "$value"
}

update_env_file() {
    if [[ "$PERSIST_TO_ENV" != true ]]; then
        return
    fi
    
    log_step "Updating .env file..."
    
    local repo_root
    repo_root=$(get_repo_root)
    local env_file="$repo_root/.env"
    
    # Keys to manage
    local managed_keys=("OPENAI_API_KEY" "LLM_PROVIDER" "AZURE_OPENAI_API_KEY" "AZURE_OPENAI_ENDPOINT" "AZURE_OPENAI_DEPLOYMENT")
    
    # Create temporary file
    local temp_file
    temp_file=$(mktemp)
    
    # Filter out managed keys from existing content
    if [[ -f "$env_file" ]]; then
        while IFS= read -r line; do
            local should_keep=true
            for key in "${managed_keys[@]}"; do
                if [[ "$line" =~ ^${key}= ]]; then
                    should_keep=false
                    break
                fi
            done
            if [[ "$should_keep" == true ]]; then
                echo "$line" >> "$temp_file"
            fi
        done < "$env_file"
    fi
    
    # Add new variables
    if [[ -n "$OPENAI_KEY" ]]; then
        echo "OPENAI_API_KEY=$OPENAI_KEY" >> "$temp_file"
    fi
    if [[ "$PROVIDER" == "openai" ]]; then
        echo "LLM_PROVIDER=openai" >> "$temp_file"
    elif [[ "$PROVIDER" == "azure" ]]; then
        echo "LLM_PROVIDER=azure" >> "$temp_file"
        if [[ -n "$AZURE_KEY" ]]; then
            echo "AZURE_OPENAI_API_KEY=$AZURE_KEY" >> "$temp_file"
        fi
        if [[ -n "$AZURE_ENDPOINT" ]]; then
            echo "AZURE_OPENAI_ENDPOINT=$AZURE_ENDPOINT" >> "$temp_file"
        fi
        if [[ -n "$AZURE_DEPLOYMENT" ]]; then
            echo "AZURE_OPENAI_DEPLOYMENT=$AZURE_DEPLOYMENT" >> "$temp_file"
        fi
    fi
    
    # Move temp file to final location
    mv "$temp_file" "$env_file"
    
    log_success ".env file updated at: $env_file"
}

set_environment_variables() {
    log_step "Setting environment variables (scope: $SCOPE)..."
    
    # Set for current session
    if [[ -n "$OPENAI_KEY" ]]; then
        export OPENAI_API_KEY="$OPENAI_KEY"
    fi
    
    if [[ "$PROVIDER" == "openai" ]]; then
        export LLM_PROVIDER="openai"
    elif [[ "$PROVIDER" == "azure" ]]; then
        export LLM_PROVIDER="azure"
        if [[ -n "$AZURE_KEY" ]]; then
            export AZURE_OPENAI_API_KEY="$AZURE_KEY"
        fi
        if [[ -n "$AZURE_ENDPOINT" ]]; then
            export AZURE_OPENAI_ENDPOINT="$AZURE_ENDPOINT"
        fi
        if [[ -n "$AZURE_DEPLOYMENT" ]]; then
            export AZURE_OPENAI_DEPLOYMENT="$AZURE_DEPLOYMENT"
        fi
    fi
    
    # For user scope, add to shell profile (simplified approach)
    if [[ "$SCOPE" == "user" ]]; then
        local profile_file="$HOME/.bashrc"
        if [[ "$SHELL" == *"zsh"* ]]; then
            profile_file="$HOME/.zshrc"
        fi
        
        log_step "Adding environment variables to $profile_file..."
        
        # Remove existing entries
        local managed_keys=("OPENAI_API_KEY" "LLM_PROVIDER" "AZURE_OPENAI_API_KEY" "AZURE_OPENAI_ENDPOINT" "AZURE_OPENAI_DEPLOYMENT")
        for key in "${managed_keys[@]}"; do
            if [[ -f "$profile_file" ]]; then
                sed -i.bak "/^export $key=/d" "$profile_file" 2>/dev/null || true
            fi
        done
        
        # Add new entries
        if [[ -n "$OPENAI_KEY" ]]; then
            echo "export OPENAI_API_KEY=\"$OPENAI_KEY\"" >> "$profile_file"
        fi
        echo "export LLM_PROVIDER=\"$PROVIDER\"" >> "$profile_file"
        
        if [[ "$PROVIDER" == "azure" ]]; then
            if [[ -n "$AZURE_KEY" ]]; then
                echo "export AZURE_OPENAI_API_KEY=\"$AZURE_KEY\"" >> "$profile_file"
            fi
            if [[ -n "$AZURE_ENDPOINT" ]]; then
                echo "export AZURE_OPENAI_ENDPOINT=\"$AZURE_ENDPOINT\"" >> "$profile_file"
            fi
            if [[ -n "$AZURE_DEPLOYMENT" ]]; then
                echo "export AZURE_OPENAI_DEPLOYMENT=\"$AZURE_DEPLOYMENT\"" >> "$profile_file"
            fi
        fi
        
        log_success "Environment variables added to $profile_file (will take effect in new shell sessions)"
    fi
    
    log_success "Environment variables set for current session"
}

remove_environment_variables() {
    log_step "Removing environment variables..."
    
    # Remove from current session
    unset OPENAI_API_KEY LLM_PROVIDER AZURE_OPENAI_API_KEY AZURE_OPENAI_ENDPOINT AZURE_OPENAI_DEPLOYMENT 2>/dev/null || true
    
    # Remove from user profile
    local profile_file="$HOME/.bashrc"
    if [[ "$SHELL" == *"zsh"* ]]; then
        profile_file="$HOME/.zshrc"
    fi
    
    if [[ -f "$profile_file" ]]; then
        local managed_keys=("OPENAI_API_KEY" "LLM_PROVIDER" "AZURE_OPENAI_API_KEY" "AZURE_OPENAI_ENDPOINT" "AZURE_OPENAI_DEPLOYMENT")
        for key in "${managed_keys[@]}"; do
            sed -i.bak "/^export $key=/d" "$profile_file" 2>/dev/null || true
        done
    fi
    
    log_success "Environment variables removed"
}

remove_from_env_file() {
    if [[ "$PERSIST_TO_ENV" != true ]]; then
        return
    fi
    
    log_step "Removing keys from .env file..."
    
    local repo_root
    repo_root=$(get_repo_root)
    local env_file="$repo_root/.env"
    
    if [[ ! -f "$env_file" ]]; then
        log_warning ".env file does not exist"
        return
    fi
    
    # Create temporary file
    local temp_file
    temp_file=$(mktemp)
    
    # Filter out managed keys
    local managed_keys=("OPENAI_API_KEY" "LLM_PROVIDER" "AZURE_OPENAI_API_KEY" "AZURE_OPENAI_ENDPOINT" "AZURE_OPENAI_DEPLOYMENT")
    while IFS= read -r line; do
        local should_keep=true
        for key in "${managed_keys[@]}"; do
            if [[ "$line" =~ ^${key}= ]]; then
                should_keep=false
                break
            fi
        done
        if [[ "$should_keep" == true ]]; then
            echo "$line" >> "$temp_file"
        fi
    done < "$env_file"
    
    # Move temp file to final location
    mv "$temp_file" "$env_file"
    
    log_success "Keys removed from .env file"
}

test_connectivity() {
    log_step "Testing LLM connectivity..."
    
    local repo_root
    repo_root=$(get_repo_root)
    local test_script="$repo_root/scripts/test_llm_connectivity.py"
    
    if [[ ! -f "$test_script" ]]; then
        log_warning "Connectivity test script not found: $test_script"
        return
    fi
    
    echo -e "${GRAY}Running connectivity test...${NC}"
    
    if python "$test_script"; then
        log_success "Connectivity test completed successfully"
    else
        log_warning "Connectivity test failed"
        echo -e "${YELLOW}Troubleshooting suggestions:${NC}"
        echo -e "${GRAY}1. Check your internet connection${NC}"
        echo -e "${GRAY}2. Verify API key is valid and has quota${NC}"
        echo -e "${GRAY}3. Check if corporate proxy/firewall blocks OpenAI${NC}"
        echo -e "${GRAY}4. Ensure API key format is correct (starts with 'sk-')${NC}"
    fi
}

show_configuration() {
    log_step "Current configuration:"
    
    if [[ -n "$OPENAI_KEY" ]]; then
        local masked
        masked=$(get_masked_key "$OPENAI_KEY")
        echo -e "${GRAY}  OPENAI_API_KEY = $masked${NC}"
    fi
    
    if [[ -n "$AZURE_KEY" ]]; then
        local masked
        masked=$(get_masked_key "$AZURE_KEY")
        echo -e "${GRAY}  AZURE_OPENAI_API_KEY = $masked${NC}"
    fi
    
    if [[ -n "$AZURE_ENDPOINT" ]]; then
        echo -e "${GRAY}  AZURE_OPENAI_ENDPOINT = $AZURE_ENDPOINT${NC}"
    fi
    
    if [[ -n "$AZURE_DEPLOYMENT" ]]; then
        echo -e "${GRAY}  AZURE_OPENAI_DEPLOYMENT = $AZURE_DEPLOYMENT${NC}"
    fi
    
    echo -e "${GRAY}  LLM_PROVIDER = $PROVIDER${NC}"
    echo -e "${GRAY}  Scope: $SCOPE${NC}"
    echo -e "${GRAY}  Persist to .env: $PERSIST_TO_ENV${NC}"
}

# Main execution
main() {
    echo -e "${MAGENTA}MAO-Wise LLM API Keys Configuration${NC}"
    echo "================================================"
    
    # Ensure .gitignore is properly configured
    ensure_gitignore
    
    if [[ "$UNSET" == true ]]; then
        log_step "Removing API keys..."
        
        remove_environment_variables
        remove_from_env_file
        
        log_success "API keys have been removed"
        return
    fi
    
    # Validate provider
    if [[ "$PROVIDER" != "openai" && "$PROVIDER" != "azure" ]]; then
        log_error "Invalid provider: $PROVIDER. Must be 'openai' or 'azure'"
        exit 1
    fi
    
    # Handle OpenAI provider
    if [[ "$PROVIDER" == "openai" ]]; then
        if [[ -z "$OPENAI_KEY" ]]; then
            echo -e "${YELLOW}OpenAI API Key is required for this provider.${NC}"
            OPENAI_KEY=$(get_secure_input "Enter your OpenAI API Key")
            
            if [[ -z "$OPENAI_KEY" ]]; then
                log_error "OpenAI API Key is required"
                exit 1
            fi
        fi
        
        # Validate OpenAI key format
        if [[ ! "$OPENAI_KEY" =~ ^sk- ]]; then
            log_warning "OpenAI API Key should start with 'sk-'"
        fi
    fi
    
    # Handle Azure provider
    if [[ "$PROVIDER" == "azure" ]]; then
        if [[ -z "$AZURE_KEY" ]]; then
            echo -e "${YELLOW}Azure OpenAI API Key is required for this provider.${NC}"
            AZURE_KEY=$(get_secure_input "Enter your Azure OpenAI API Key")
        fi
        
        if [[ -z "$AZURE_ENDPOINT" ]]; then
            echo -n -e "${YELLOW}Enter your Azure OpenAI Endpoint: ${NC}"
            read -r AZURE_ENDPOINT
        fi
        
        if [[ -z "$AZURE_DEPLOYMENT" ]]; then
            echo -n -e "${YELLOW}Enter your Azure OpenAI Deployment name: ${NC}"
            read -r AZURE_DEPLOYMENT
        fi
        
        if [[ -z "$AZURE_KEY" || -z "$AZURE_ENDPOINT" || -z "$AZURE_DEPLOYMENT" ]]; then
            log_error "Azure provider requires API key, endpoint, and deployment name"
            exit 1
        fi
    fi
    
    # Show configuration (with masked keys)
    show_configuration
    
    # Update environment variables
    set_environment_variables
    
    # Update .env file
    update_env_file
    
    log_success "API keys configured successfully!"
    
    # Test connectivity for OpenAI
    if [[ "$PROVIDER" == "openai" ]]; then
        test_connectivity
    fi
}

# Run main function
main
