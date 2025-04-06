#!/bin/bash

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Log functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Backup current system preferences
backup_preferences() {
    local backup_dir="$HOME/.mac-setup-backup/$(date +%Y%m%d_%H%M%S)"
    log_info "Backing up current system preferences to $backup_dir"
    
    mkdir -p "$backup_dir"
    
    # Backup dock preferences
    defaults export com.apple.dock "$backup_dir/dock.plist"
    
    # Backup finder preferences
    defaults export com.apple.finder "$backup_dir/finder.plist"
    
    # Backup global preferences
    defaults export NSGlobalDomain "$backup_dir/global.plist"
    
    log_info "Preferences backup completed"
}
# Check if running on macOS
check_macos() {
    if [[ "$(uname)" != "Darwin" ]]; then
        log_error "This script is only for macOS"
        exit 1
    fi
}

# Check for internet connection
check_internet() {
    log_info "Checking internet connection..."
    if ! ping -c 1 google.com &> /dev/null; then
        log_error "No internet connection detected"
        exit 1
    fi
}

# Install Homebrew if not already installed
install_homebrew() {
    if ! command -v brew &> /dev/null; then
        log_info "Installing Homebrew..."
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
        
        # Add Homebrew to PATH for arm64 Macs
        if [[ "$(uname -m)" == "arm64" ]]; then
            echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zshrc
            eval "$(/opt/homebrew/bin/brew shellenv)"
        fi
    else
        log_info "Homebrew is already installed"
    fi
}

# Install Ansible
install_ansible() {
    if ! command -v ansible &> /dev/null; then
        log_info "Installing Ansible..."
        brew install ansible
    else
        log_info "Ansible is already installed"
    fi
}

# Clone required repositories
clone_repositories() {
    local temp_dir="/tmp/mac-setup"
    mkdir -p "$temp_dir"
    
    log_info "Cloning required repositories..."
    
    # Clone dotfiles repository
    if [ ! -d "$temp_dir/dotfiles" ]; then
        git clone https://github.com/thesammykins/dotfiles.git "$temp_dir/dotfiles"
    fi
    
    # Clone brewfile repositories
    if [ ! -d "$temp_dir/brewfile" ]; then
        git clone https://github.com/thesammykins/brewfile.git "$temp_dir/brewfile"
    fi
    
    if [ ! -d "$temp_dir/brewfile-per" ]; then
        git clone https://github.com/thesammykins/brewfile-per.git "$temp_dir/brewfile-per"
    fi
}

# Select configuration type
select_configuration() {
    echo "Please select your configuration type:"
    echo "1) Work Device"
    echo "2) Personal Device"
    
    while true; do
        read -p "Enter your choice (1 or 2): " choice
        case $choice in
            1)
                echo "work"
                return
                ;;
            2)
                echo "personal"
                return
                ;;
            *)
                log_error "Invalid choice. Please enter 1 or 2"
                ;;
        esac
    done
}

# Print setup summary
print_summary() {
    local config_type="$1"
    
    log_info "Setup Summary:"
    echo "----------------------------------------"
    echo "Configuration type: $config_type"
    echo "Dotfiles installed from: thesammykins/dotfiles"
    echo "Brewfile used: thesammykins/brewfile${config_type == 'personal' && echo '-per' || echo ''}"
    echo "System preferences backed up to: $HOME/.mac-setup-backup/"
    echo "----------------------------------------"
    echo "Next steps:"
    echo "1. Restart your Mac to apply all changes"
    echo "2. Check your terminal configuration"
    echo "3. Verify installed applications"
    echo "----------------------------------------"
}
# Main script execution
main() {
    log_info "Starting Mac setup script..."
    
    # Run checks
    check_macos
    check_internet
    
    # Install required tools
    install_homebrew
    install_ansible
    
    # Clone repositories
    clone_repositories
    
    # Get configuration type
    config_type=$(select_configuration)
    
    log_info "Selected configuration: $config_type"
    
    # Backup current preferences
    backup_preferences
    
    # Create Ansible playbook based on configuration
    if [ "$config_type" == "work" ]; then
        ansible-playbook -i playbooks/inventory/hosts playbooks/work-setup.yml || {
            log_error "Work setup playbook failed"
            exit 1
        }
    else
        ansible-playbook -i playbooks/inventory/hosts playbooks/personal-setup.yml || {
            log_error "Personal setup playbook failed"
            exit 1
        }
    fi
    
    log_info "Setup completed successfully!"
    print_summary "$config_type"
    log_info "Please restart your Mac to ensure all changes take effect."
}

# Run main function
main "$@"

