#!/bin/bash

# ============================================
# Sycord M1 Instance - Auto Deploy Starter
# This script sets up and runs the deployment server
# with automatic Wrangler installation
# ============================================

set -euo pipefail

echo "╔════════════════════════════════════════════════════════════╗"
echo "║          Sycord M1 Instance - Deployment Server            ║"
echo "║              Auto Deploy Starter Script                     ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored messages
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running as root
if [ "$EUID" -eq 0 ]; then
    print_warning "Running as root. Consider running as a regular user."
fi

# Step 1: Check for Python
print_status "Checking Python installation..."
if command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
    print_success "Python3 found: $(python3 --version)"
elif command -v python &> /dev/null; then
    PYTHON_CMD="python"
    print_success "Python found: $(python --version)"
else
    print_error "Python not found. Please install Python 3.8 or higher."
    exit 1
fi

# Step 2: Check for Node.js and npm
print_status "Checking Node.js installation..."
if command -v node &> /dev/null; then
    print_success "Node.js found: $(node --version)"
else
    print_warning "Node.js not found. Installing Node.js..."
    
    # Check OS and install Node.js
    if [ "$(uname)" == "Darwin" ]; then
        # macOS
        if command -v brew &> /dev/null; then
            brew install node
        else
            print_error "Please install Homebrew first: https://brew.sh/"
            exit 1
        fi
    elif [ -f /etc/debian_version ]; then
        # Debian/Ubuntu
        curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
        sudo apt-get install -y nodejs
    elif [ -f /etc/redhat-release ]; then
        # RHEL/CentOS
        curl -fsSL https://rpm.nodesource.com/setup_18.x | sudo bash -
        sudo yum install -y nodejs
    else
        print_error "Unsupported OS. Please install Node.js manually."
        exit 1
    fi
    
    print_success "Node.js installed: $(node --version)"
fi

# Step 3: Check for npm
print_status "Checking npm installation..."
if command -v npm &> /dev/null; then
    print_success "npm found: $(npm --version)"
else
    print_error "npm not found. Please install npm."
    exit 1
fi

# Step 4: Install Wrangler CLI
print_status "Checking Wrangler CLI installation..."
if command -v wrangler &> /dev/null; then
    print_success "Wrangler found: $(wrangler --version 2>&1 | head -1)"
else
    print_status "Installing Wrangler CLI globally..."
    npm install -g wrangler
    
    if command -v wrangler &> /dev/null; then
        print_success "Wrangler installed: $(wrangler --version 2>&1 | head -1)"
    else
        print_error "Failed to install Wrangler. Please install manually: npm install -g wrangler"
        exit 1
    fi
fi

# Step 5: Create virtual environment if not exists
print_status "Setting up Python virtual environment..."
if [ ! -d "venv" ]; then
    $PYTHON_CMD -m venv venv
    print_success "Virtual environment created"
else
    print_status "Virtual environment already exists"
fi

# Step 6: Activate virtual environment and install dependencies
print_status "Installing Python dependencies..."
source venv/bin/activate

if ! pip install --upgrade pip; then
    print_error "Failed to upgrade pip"
    exit 1
fi

if ! pip install -r requirements.txt; then
    print_error "Failed to install Python dependencies"
    exit 1
fi

print_success "Python dependencies installed"

# Step 7: Check for .env file
print_status "Checking environment configuration..."
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        print_warning ".env file not found. Copying from .env.example..."
        cp .env.example .env
        print_warning "Please edit .env file with your configuration before running."
        echo ""
        echo "Required configuration:"
        echo "  - MONGO_URI: MongoDB connection string"
        echo "  - MONGO_DB: Database name (default: test)"
        echo "  - MONGO_COLLECTION: Collection name (default: github_tokens)"
        echo "  - PROJECT_ID: MongoDB ObjectId for GitHub token lookup"
        echo "  - CLOUDFLARE_API_TOKEN: Cloudflare API token"
        echo "  - CLOUDFLARE_ACCOUNT_ID: Cloudflare account ID"
        echo ""
    else
        print_error ".env file not found and .env.example is missing."
        exit 1
    fi
else
    print_success "Environment configuration found"
fi

# Step 8: Start the server
echo ""
echo "╔════════════════════════════════════════════════════════════╗"
echo "║                   Starting M1 Instance                      ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

print_status "Starting Sycord Deployment Server..."
print_status "Access the UI at: http://localhost:${PORT:-5000}"
echo ""

# Run the Flask application
$PYTHON_CMD app.py
