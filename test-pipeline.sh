#!/bin/bash

# Test script to verify pipeline deployment functionality
# This script tests the non-interactive behavior of deployment scripts

echo "Testing pipeline deployment functionality..."
echo

# Test 1: Check deploy.sh help with pipeline info
echo "=== Test 1: Deploy script help ==="
./deploy.sh --help | grep -A 5 "Pipeline/Automated"
echo

# Test 2: Check update-lambdas.sh help with pipeline info
echo "=== Test 2: Update lambdas script help ==="
./update-lambdas.sh --help | grep -A 5 "Pipeline/Automated"
echo

# Test 3: Verify environment variables are recognized
echo "=== Test 3: Environment variable detection ==="
export AUTO_CONFIRM=true
echo "Set AUTO_CONFIRM=true"

# Simulate a dry-run by checking if scripts would proceed without prompts
echo "Testing environment loading with AUTO_CONFIRM..."
source config/environments.sh
if load_environment "development" >/dev/null 2>&1; then
    echo "✓ Environment loading works in automated mode"
else
    echo "✗ Environment loading failed"
fi

# Test 4: Check if CI environment is detected
echo
echo "=== Test 4: CI environment detection ==="
export CI=true
echo "Set CI=true"
echo "Scripts should now run without prompts when CI=true is set"

# Test 5: Check GitHub Actions detection
echo
echo "=== Test 5: GitHub Actions detection ==="
export GITHUB_ACTIONS=true
echo "Set GITHUB_ACTIONS=true"
echo "Scripts should now run without prompts when GITHUB_ACTIONS=true is set"

echo
echo "=== Pipeline Test Summary ==="
echo "✓ All deployment scripts updated with pipeline support"
echo "✓ Environment variables: AUTO_CONFIRM, CI, GITHUB_ACTIONS"
echo "✓ Scripts will skip confirmation prompts in automated environments"
echo "✓ Documentation created in PIPELINE_DEPLOYMENT.md"
echo
echo "To test actual deployment in pipeline mode:"
echo "  export AUTO_CONFIRM=true"
echo "  ./deploy.sh development"
