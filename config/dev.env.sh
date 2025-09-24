#!/bin/bash

# Development Environment Specific Configuration
# This file is sourced only when deploying to development environment
# Use this file to override default behavior for development deployments

# Skip Lambda function packaging and updates during development deployments
# Set to "true" to skip Lambda updates, "false" to include them
# This is useful for faster deployments when only infrastructure changes are needed
SKIP_LAMBDAS==false

# Example usage scenarios:
# - SKIP_LAMBDAS=true  : Skip Lambda updates for faster infrastructure-only deployments
# - SKIP_LAMBDAS=false : Include Lambda updates (default behavior)

# Other development-specific overrides can be added here
# DEBUG_MODE=true
# VERBOSE_LOGGING=true
# DEVELOPMENT_ONLY_FEATURES=true

# Note: This file is only loaded for development environment deployments.
# Production deployments will always include all Lambda function updates for safety.

