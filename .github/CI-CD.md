# CI/CD Documentation

This document explains the continuous integration and deployment setup for Auto Lab Solutions Backend.

## Overview

The CI/CD pipeline uses GitHub Actions to automatically deploy the backend infrastructure and Lambda functions to AWS. It supports two environments:

- **Development**: Deployed from `dev` branch
- **Production**: Deployed from `prod` branch

## Workflow Files

### 1. `deploy-dev.yml` - Development Deployment
**Trigger**: Push to `dev` branch
**Environment**: Development

**Jobs**:
- **Validate**: Syntax checking and template validation
- **Deploy**: Full infrastructure deployment to development
- **Test**: Basic integration tests

**Features**:
- Automatic deployment on code push
- Infrastructure validation
- Basic health checks
- Integration testing

### 2. `deploy-prod.yml` - Production Deployment
**Trigger**: Push to `prod` branch
**Environment**: Production

**Jobs**:
- **Validate**: Syntax checking and template validation
- **Security-check**: Security scanning with Bandit and Safety
- **Deploy**: Full infrastructure deployment to production
- **Post-deploy-tests**: Production health checks

**Features**:
- Security scanning before deployment
- Pre-deployment backup
- Production environment protection
- Comprehensive health checks
- Post-deployment notifications

### 3. `update-lambdas.yml` - Lambda Function Updates
**Trigger**: Manual (workflow_dispatch)
**Environment**: Configurable (dev/prod)

**Features**:
- Fast Lambda-only updates
- Choose specific functions or all functions
- Environment selection
- Syntax validation
- Function testing

### 4. `cleanup.yml` - Environment Cleanup
**Trigger**: Manual (workflow_dispatch)
**Environment**: Configurable (dev/prod)

**Features**:
- Complete environment cleanup
- Confirmation required ("DELETE")
- Pre-cleanup backup
- Resource verification
- Artifact backup

## Branch Strategy

### Development Workflow
```
feature branch → dev branch → development environment
```

1. Create feature branches from `dev`
2. Push changes to feature branch
3. Create PR to `dev` branch
4. After merge, automatic deployment to development
5. Test in development environment

### Production Workflow
```
dev branch → prod branch → production environment
```

1. After testing in development, create PR from `dev` to `prod`
2. Require code reviews and approvals
3. After merge, automatic deployment to production
4. Production health checks and monitoring

## Environment Configuration

### Automatic Environment Detection
The scripts automatically detect the environment based on:

1. `AUTO_LAB_ENV` environment variable
2. GitHub Actions `ENVIRONMENT` variable
3. Default to development

### Environment-Specific Resources

#### Development
- Stack: `auto-lab-backend-dev`
- S3 Bucket: `auto-lab-reports-dev`
- Tables: `*-development` suffix
- Functions: `*-development` suffix

#### Production
- Stack: `auto-lab-backend`
- S3 Bucket: `auto-lab-reports`
- Tables: `*-production` suffix
- Functions: `*-production` suffix

## Security Features

### Development Environment
- Basic syntax validation
- Integration testing
- Automatic deployment

### Production Environment
- Security scanning with Bandit
- Dependency vulnerability checking with Safety
- Manual approval required (GitHub Environment protection)
- Pre-deployment backup
- Comprehensive health checks

## Usage Examples

### Deploying to Development
```bash
# Push to dev branch
git push origin dev

# Workflow automatically:
# 1. Validates code
# 2. Deploys to development
# 3. Runs integration tests
```

### Deploying to Production
```bash
# Create PR from dev to prod
gh pr create --base prod --head dev --title "Release v1.0.0"

# After approval and merge:
# 1. Security scan
# 2. Deploy to production
# 3. Health checks
```

### Updating Lambda Functions Only
```bash
# Via GitHub Actions UI:
# 1. Go to Actions tab
# 2. Select "Update Lambda Functions"
# 3. Click "Run workflow"
# 4. Choose environment and functions
# 5. Click "Run workflow"
```

### Manual Cleanup
```bash
# Via GitHub Actions UI:
# 1. Go to Actions tab
# 2. Select "Cleanup Environment"
# 3. Click "Run workflow"
# 4. Choose environment
# 5. Type "DELETE" to confirm
# 6. Click "Run workflow"
```

## Monitoring and Debugging

### Workflow Status
- Check GitHub Actions tab for deployment status
- View logs for detailed information
- Get notifications on failures

### Deployed Resources
```bash
# Check deployment status (if running locally)
./dev-tools.sh --env development status
./dev-tools.sh --env production status

# Get API endpoints
./dev-tools.sh --env development endpoints
./dev-tools.sh --env production endpoints
```

### Function Logs
```bash
# View Lambda function logs (if running locally)
./dev-tools.sh --env development logs api-get-prices
./dev-tools.sh --env production logs api-get-prices
```

## Troubleshooting

### Common Issues

1. **Deployment Failed**
   - Check AWS credentials in secrets
   - Verify IAM permissions
   - Check CloudFormation limits

2. **Lambda Update Failed**
   - Check function names
   - Verify function exists in target environment
   - Check package size limits

3. **Security Scan Failed**
   - Review Bandit security report
   - Fix security vulnerabilities
   - Update dependencies

4. **Health Check Failed**
   - Check Lambda function configuration
   - Verify API Gateway integration
   - Check DynamoDB table status

### Getting Help

1. **Workflow Logs**: Check detailed logs in GitHub Actions
2. **AWS Console**: Verify resources in AWS console
3. **Local Testing**: Use dev-tools.sh for local debugging
4. **CloudFormation**: Check stack events for detailed errors

## Best Practices

### Development
- Test changes in development first
- Use descriptive commit messages
- Create focused pull requests
- Review code before merging

### Production
- Always deploy to development first
- Require code reviews for production
- Monitor deployments closely
- Have rollback plan ready

### Security
- Keep dependencies updated
- Review security scan results
- Use separate AWS accounts for environments
- Regularly rotate access keys

### Monitoring
- Set up CloudWatch alarms
- Monitor API Gateway metrics
- Track Lambda function errors
- Set up billing alerts
