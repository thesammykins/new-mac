# New Mac Setup Script

This repository contains scripts and playbooks to automate the setup of a new Mac device. It supports different configuration types including personal and work setups.

## Prerequisites

- A fresh installation of macOS
- Administrative access to the device
- Internet connection

## Features

- Automated installation of Homebrew
- Configurable setup types:
  - Work device configuration
  - Personal device configuration
- Automatic installation of:
  - Dotfiles from [thesammykins/dotfiles](https://github.com/thesammykins/dotfiles)
  - Work-related applications from [thesammykins/brewfile](https://github.com/thesammykins/brewfile)
  - Personal applications from [thesammykins/brewfile-per](https://github.com/thesammykins/brewfile-per)
- System preferences configuration

## Getting Started

1. Clone this repository:
   ```bash
   git clone https://github.com/thesammykins/new-mac.git
   cd new-mac
   ```

2. Make the setup script executable:
   ```bash
   chmod +x setup.sh
   ```

3. Run the setup script:
   ```bash
   ./setup.sh
   ```

4. Follow the prompts to select your desired configuration type:
   - Work device setup
   - Personal device setup

## What Gets Installed

### Work Device Setup
- All dotfiles from thesammykins/dotfiles
- Applications and tools from thesammykins/brewfile
- Standard work system preferences

### Personal Device Setup
- All dotfiles from thesammykins/dotfiles
- Applications and tools from thesammykins/brewfile-per
- Personal system preferences

## Post-Installation

After the script completes:
1. Restart your Mac to ensure all changes take effect
2. Check that all applications were installed correctly
3. Verify system preferences were applied

## Troubleshooting

If you encounter any issues during installation:
1. Check your internet connection
2. Ensure you have administrative privileges
3. Review the logs in the terminal output
4. Create an issue in this repository if the problem persists

## Contributing

Feel free to submit issues and enhancement requests!

## License

[MIT License](LICENSE)

