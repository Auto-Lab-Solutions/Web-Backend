# Auto Lab Solutions - Backend

[![Deploy to Development](https://github.com/YOUR_USERNAME/Auto-Lab-Solutions/actions/workflows/deploy-dev.yml/badge.svg)](https://github.com/YOUR_USERNAME/Auto-Lab-Solutions/actions/workflows/deploy-dev.yml)
[![Deploy to Produ- 📊 Infrastructure impact and monitoring

## 📊 Post-Deployment Configuration//github.com/YOUR_USERNAME/Auto-Lab-Solutions/actions/workflows/deploy-prod.yml/badge.svg)](https://github.com/YOUR_USERNAME/Auto-Lab-Solutions/actions/workflows/deploy-prod.yml)

This repository contains the complete backend infrastructure for the Auto Lab Solutions platform, deployed on AWS using serverless technologies.

## Architecture Overview

The backend consists of the following components:

### 🗄️ **Data Layer**
- **DynamoDB Tables**: 10 tables storing all application data
  - Staff, Users, Appointments, Orders, Inquiries
  - Messages, Connections, UnavailableSlots
  - ItemPrices, ServicePrices

### ⚡ **Compute Layer**
- **Lambda Functions**: 30+ serverless functions handling:
  - REST API endpoints (`api-*`)
  - WebSocket handlers (`ws-*`)
  - Custom authorizers (`staff-authorizer*`)
  - Async processors (`sqs-process-*`)

### 📬 **Asynchronous Notification System**
- **SQS Queues**: Decoupled notification processing
  - Email notification queue with DLQ
  - Firebase notification queue with DLQ (optional)
- **Notification Processors**: Dedicated Lambda functions
  - Email notification processor
  - Firebase notification processor (optional)
- **WebSocket Notifications**: Real-time messaging (synchronous for messaging scenarios only)
- **Notification Utils**: Shared library for queueing notifications

### 🌐 **API Layer**
- **REST API Gateway**: RESTful endpoints for CRUD operations
- **WebSocket API Gateway**: Real-time communication features

### 📁 **Storage & CDN**
- **S3 Bucket**: Secure storage for reports and files
- **CloudFront**: Global content delivery network

### 🔐 **Authentication**
- **Auth0 Integration**: JWT-based authentication
- **Custom Authorizers**: Role-based access control

## 🚀 Quick Start

### Prerequisites

1. **AWS CLI** configured with appropriate permissions
   ```bash
   aws configure
   ```

2. **Python 3.13** installed
   ```bash
   python3 --version
   ```

3. **Required permissions**: Your AWS account needs permissions for:
   - CloudFormation
   - Lambda
   - API Gateway
   - DynamoDB
   - S3
   - CloudFront
   - IAM

### 🌍 Multi-Environment Support

The deployment system supports multiple environments (development and production) with environment-specific resources and configurations.

#### Environment Configuration

Each environment has its own:
- **Stack names** (e.g., `auto-lab-backend-dev` vs `auto-lab-backend`)
- **S3 buckets** (e.g., `auto-lab-reports-<account-id>-dev` vs `auto-lab-reports-<account-id>-production`)
- **DynamoDB tables** (e.g., `Users-development` vs `Users-production`)
- **Lambda functions** (e.g., `api-get-users-development` vs `api-get-users-production`)
- **Resource settings** (memory, timeouts, log levels)

#### Set Default Environment

```bash
# Set development as default (recommended for initial setup)
./config/environments.sh set development

# Set production as default
./config/environments.sh set production

# View current environment configuration
./config/environments.sh show
```

### 🔧 One-Command Local Deployment

```bash
# Make scripts executable
chmod +x *.sh

# Deploy to development environment (default)
./deploy.sh

# Deploy to specific environment
./deploy.sh --env development
./deploy.sh --env production
```

This single command will:
1. ✅ Check prerequisites
2. 📦 Create S3 bucket for templates  
3. 🚀 Upload CloudFormation templates
4. 📋 Package all Lambda functions
5. 🏗️ Deploy complete infrastructure
6. 🔗 Configure API Gateway integrations
7. ⚙️ Set up environment variables
8. 📝 Provide deployment summary

### 📋 Individual Scripts

All scripts support the `--env` parameter for multi-environment deployment:

```bash
# Upload CloudFormation templates only
./upload-templates.sh --env development

# Update Lambda functions only (fast updates)
./update-websocket-endpoints.sh --env production

# Update only Lambda functions (faster for code changes)
./update-lambdas.sh --env dev --all
./update-lambdas.sh --env prod api-get-prices api-get-users

# Development tools
./dev-tools.sh --env dev status
./dev-tools.sh --env prod endpoints
./dev-tools.sh --env dev logs api-get-prices

# Validate deployment
./validate-deployment.sh --env development

# Validate notification system specifically
./validate-notification-system.sh --env development

# Clean up all resources
./cleanup.sh --env development
```

## ⚡ **Lambda Function Updates**

For faster development when you only change Lambda code:

### **Update All Functions**
```bash
./update-lambdas.sh --env dev --all
./update-lambdas.sh --env production --all
```

### **Update Specific Functions**
```bash
./update-lambdas.sh --env dev api-get-prices api-get-users ws-connect
./update-lambdas.sh --env prod api-get-prices api-get-users ws-connect
```

### **List Available Functions**
```bash
./update-lambdas.sh --list
```

**Benefits:**
- ⚡ **10x faster** than full infrastructure deployment
- 🎯 **Targeted updates** - only affected functions
- ✅ **Preserves infrastructure** - no risk of configuration changes
- 🔄 **Automatic packaging** - handles dependencies and common libraries

## 🛠️ **Development Tools**

Use the development tools script for debugging and monitoring:

### **Check Deployment Status**
```bash
./dev-tools.sh --env dev status
./dev-tools.sh --env production status
./dev-tools.sh status
```

### **Get API Endpoints**
```bash
./dev-tools.sh --env dev endpoints
./dev-tools.sh --env production endpoints
```

### **View Function Logs**
```bash
./dev-tools.sh --env dev logs api-get-prices
./dev-tools.sh --env dev watch api-get-prices  # Real-time logs
```

### **Test Functions**
```bash
./dev-tools.sh --env dev test api-get-users
./dev-tools.sh --env production test api-get-users
```

### **Check Environment Variables**
```bash
./dev-tools.sh --env dev env api-get-prices
./dev-tools.sh --env production env api-get-prices
```

## � **Firebase Cloud Messaging (Optional)**

Firebase notifications are **completely optional** and configured centrally per environment.

### **Default Behavior**
- ✅ **Development**: Firebase DISABLED (simpler setup, faster deployment)
- ✅ **Production**: Firebase ENABLED (full feature set)
- ✅ **All other notifications work normally** (Email, WebSocket)

### **Configuration Overview**

Firebase is controlled in `config/environments.sh` with environment-specific defaults:
- **Enable/Disable state**: Set per environment in configuration file
- **Firebase credentials**: Passed from CI/CD or environment variables

### **Quick Setup**

```bash
# For CI/CD: Set GitHub repository secrets/variables
# FIREBASE_PROJECT_ID_DEV, FIREBASE_PROJECT_ID_PROD (variables)
# FIREBASE_SERVICE_ACCOUNT_KEY_DEV, FIREBASE_SERVICE_ACCOUNT_KEY_PROD (secrets)

# For local deployment: Set environment variables
export FIREBASE_PROJECT_ID="your-firebase-project-id"
export FIREBASE_SERVICE_ACCOUNT_KEY="base64-service-account-json"
./deploy.sh production
```

### **Override Environment Defaults**

```bash
# To disable Firebase in production (cost optimization)
# Edit config/environments.sh: export ENABLE_FIREBASE_NOTIFICATIONS="false"

# To enable Firebase in development (testing)
# Edit config/environments.sh: export ENABLE_FIREBASE_NOTIFICATIONS="true"
```

### **Complete Firebase Setup Guide**

For detailed Firebase configuration, testing, and troubleshooting, see:
**📋 [Firebase Complete Guide](FIREBASE_COMPLETE_GUIDE.md)**

The guide covers:
- 🏗️ Centralized configuration architecture
- 🔐 Service account setup and security
- 🔄 CI/CD pipeline integration  
- 💰 Cost optimization strategies
- 🛠️ Troubleshooting common issues
- 📊 Infrastructure impact and monitoring

### **Test Firebase Configuration**

```bash
# Test Firebase config without deploying
./test-firebase-config.sh

# Deploy with Firebase enabled
./deploy.sh production
```

## 💾 **Backup System (Optional)**

The backup system is **completely optional** and configured centrally per environment.

### **Default Behavior**
- ✅ **Development**: Backup DISABLED (simpler setup, faster deployment, no S3 costs)
- ✅ **Production**: Backup ENABLED (data protection and compliance)
- ✅ **All other features work normally** when backup is disabled

### **Configuration Overview**

Backup system is controlled in `config/environments.sh` with environment-specific defaults:
- **Enable/Disable state**: Set per environment in configuration file
- **Backup schedule**: Configurable cron expression (default: weekly)
- **S3 storage**: Uses external S3 bucket (not managed by CloudFormation)

### **Quick Setup**

```bash
# Ensure backup S3 bucket exists (must be created manually)
aws s3 mb s3://auto-lab-backups-dev-${AWS_ACCOUNT_ID}      # For development
aws s3 mb s3://auto-lab-backups-${AWS_ACCOUNT_ID}          # For production

# Deploy with backup system enabled
./deploy.sh production
```

### **Override Environment Defaults**

```bash
# To disable backup in production (cost optimization)
# Edit config/environments.sh: export ENABLE_BACKUP_SYSTEM="false"

# To enable backup in development (testing)
# Edit config/environments.sh: export ENABLE_BACKUP_SYSTEM="true"

# To change backup schedule (example: daily at 2 AM Perth time / 6 PM UTC previous day)
# Edit config/environments.sh: export BACKUP_SCHEDULE="cron(0 18 * * ? *)"
```

### **Manual Backup Operations**

```bash
# Trigger manual backup
aws lambda invoke --function-name sys-manual-backup-production \
  --payload '{"reason":"Manual backup requested"}' response.json

# List available backups  
aws s3 ls s3://auto-lab-backups-${AWS_ACCOUNT_ID}/backups/production/ --recursive

# View backup logs
./dev-tools.sh logs sys-backup
```

### **Backup Features**

When enabled, the backup system provides:
- 📅 **Scheduled backups**: Automated DynamoDB and S3 data backups
- 🔄 **Manual backups**: On-demand backup via API or CLI
- 🗑️ **Automatic cleanup**: Removes old backups based on retention policy
- 📊 **Monitoring**: CloudWatch alarms and SNS notifications
- 🚨 **Failure alerts**: Automatic notification on backup failures

## 📊 Post-Deployment Configuration

### 1. Auth0 Setup

After deployment, update your Auth0 Action with the new API Gateway endpoint:

1. Get the REST API endpoint from deployment output
2. Update `auth0-actions/post-login-roles-assignment.js`
3. Replace the `apiGwEndpoint` variable with your new endpoint

### 2. WebSocket Endpoints

**Important**: WebSocket endpoints are automatically configured during deployment. However, if you need to update them manually or troubleshoot WebSocket connectivity:

```bash
# Update WebSocket endpoints for all relevant Lambda functions
./update-websocket-endpoints.sh production

# Verify WebSocket endpoint configuration
./update-websocket-endpoints.sh --verify production

# Test what would be updated (dry run)
./update-websocket-endpoints.sh --dry-run production
```

> **Note**: The deployment process automatically handles WebSocket endpoint configuration after all CloudFormation stacks are deployed. See [WEBSOCKET_ENDPOINT_UPDATE_GUIDE.md](./WEBSOCKET_ENDPOINT_UPDATE_GUIDE.md) for detailed information.

### 3. Email Configuration (AWS SES)

The platform includes comprehensive email notification capabilities for customer communications. Set up AWS SES integration:

```bash
# Configure SES environment variables
export FROM_EMAIL="noreply@autolabsolutions.com"
# SES Region varies by environment:
# - Development: us-east-1
# - Production: ap-southeast-2
export SES_REGION="us-east-1"  # For development
# export SES_REGION="ap-southeast-2"  # For production

# Validate SES configuration
./validate-ses.sh development

# Show detailed setup instructions
./validate-ses.sh development --setup

# Test email sending
./validate-ses.sh development --test
```

📖 **Detailed SES Setup**: See [SES_SETUP_GUIDE.md](./SES_SETUP_GUIDE.md) for complete domain verification, DNS configuration, and troubleshooting.

**Email Features**:
- 📧 Appointment confirmations and updates
- 🛒 Order confirmations and status updates  
- 💳 Payment confirmation receipts
- 📄 Invoice generation and delivery
- 📋 Report upload notifications

### 4. Custom Domain Configuration (Optional)

The backend supports custom domains for API Gateway endpoints, enabling you to use your own domain names instead of the default AWS-generated URLs.

#### Prerequisites
- **Route53 Hosted Zone**: Create a hosted zone for your domain
- **ACM Certificate**: Create an SSL certificate in the same region as your API
- **Domain Ownership**: Verify domain ownership through Route53 or external DNS

#### Configuration Steps

1. **Set up your custom domain parameters** in `config/environments.sh`:

```bash
# Development environment
case $ENVIRONMENT in
    "development"|"dev")
        export API_DOMAIN_NAME="api-dev.yourdomain.com"
        export HOSTED_ZONE_ID="Z1234567890ABC"
        export API_CERTIFICATE_ARN="arn:aws:acm:us-east-1:123456789012:certificate/12345678-1234-1234-1234-123456789012"
        ;;
    "production"|"prod")  
        export API_DOMAIN_NAME="api.yourdomain.com"
        export HOSTED_ZONE_ID="Z1234567890ABC"
        export API_CERTIFICATE_ARN="arn:aws:acm:ap-southeast-2:123456789012:certificate/87654321-4321-4321-4321-210987654321"
        ;;
esac
```

2. **Deploy with custom domain support**:

```bash
# Deploy with custom domain configuration
./deploy.sh development
```

3. **Validate custom domain configuration**:

```bash
# Validate that custom domains are properly configured
./validate-deployment.sh --env development
```

#### What Gets Created

When custom domains are configured, the deployment creates:

- **API Gateway Custom Domain Names**: Both REST and WebSocket APIs get custom domain names
- **Route53 DNS Records**: A-records pointing to the API Gateway endpoints
- **Base Path Mappings**: Routes traffic from custom domains to the appropriate API stages

#### Benefits

- 🌐 **Professional URLs**: Use your branded domain for APIs
- 🔒 **SSL/TLS Encryption**: Automatic HTTPS with your ACM certificate
- 🚀 **DNS Management**: Integrated Route53 DNS management
- 📊 **Consistent Branding**: Align backend URLs with your frontend domain

#### Endpoints After Custom Domain Setup

With custom domains configured, your APIs will be available at:

- **REST API**: `https://api.yourdomain.com` (instead of `https://xyz123.execute-api.region.amazonaws.com/prod`)
- **WebSocket API**: `wss://api.yourdomain.com` (instead of `wss://xyz123.execute-api.region.amazonaws.com/prod`)

> **Note**: If custom domains are not configured, the system will fall back to using the default AWS API Gateway endpoints.

### 5. Database Initialization

Initialize your DynamoDB tables with required data:

```bash
# Example: Add staff members to Staff table
aws dynamodb put-item \
    --table-name Staff \
    --item '{
        "userEmail": {"S": "admin@autolab.com"},
        "roles": {"SS": ["admin", "mechanic"]},
        "isActive": {"BOOL": true}
    }'
```

### 6. CloudFront Distribution

Your CloudFront distribution will be available at the domain provided in the deployment output. It may take 15-20 minutes to fully deploy globally.

## 🏗️ Infrastructure Components

### DynamoDB Tables
- **Staff**: Staff member information and roles
- **Users**: Customer information
- **Appointments**: Service appointments
- **Orders**: Parts and service orders
- **Inquiries**: Customer inquiries
- **Messages**: Chat messages
- **Connections**: WebSocket connections
- **UnavailableSlots**: Mechanic availability
- **ItemPrices**: Parts pricing
- **ServicePrices**: Service pricing

### Lambda Functions

#### API Functions
- `api-get-prices`: Retrieve pricing information
- `api-get-users`: User management
- `api-get-appointments`: Appointment retrieval
- `api-create-appointment`: Appointment creation
- `api-update-appointment`: Appointment updates
- `api-get-orders`: Order management
- `api-create-order`: Order creation
- `api-update-order`: Order updates
- `api-confirm-cash-payment`: Payment processing
- `api-get-inquiries`: Inquiry management
- `api-create-inquiry`: Inquiry creation
- `api-get-analytics`: Business analytics
- `api-get-staff-roles`: Staff role management
- `api-notify`: Notification system
- `api-take-user`: User assignment
- `api-get-connections`: Connection management
- `api-get-messages`: Message retrieval
- `api-send-message`: Message sending
- `api-get-upload-url`: File upload URLs

#### WebSocket Functions
- `ws-connect`: Handle WebSocket connections
- `ws-disconnect`: Handle disconnections
- `ws-init`: Initialize user sessions
- `ws-ping`: Keep-alive functionality
- `ws-staff-init`: Initialize staff sessions

#### Authorization Functions
- `staff-authorizer`: Required staff authentication
- `staff-authorizer-optional`: Optional staff authentication

#### Asynchronous Notification System
- `sqs-process-email-notification-queue`: Email notification processor
- `sqs-process-firebase-notification-queue`: Firebase notification processor (optional)

### SQS Queues
- **Email Notification Queue**: Decoupled email processing
- **Email Notification Queue**: Decoupled email processing
- **Dead Letter Queues**: Failed notification handling
- **Invoice Generation Queue**: Async invoice processing

### Notification Features
- 📧 **Asynchronous Email Processing**: All emails sent via SQS for fast response times
- 🌐 **Real-time WebSocket Notifications**: Live updates to connected clients
- 🔄 **Retry Logic**: Automatic retry with exponential backoff
- 🚨 **Dead Letter Queues**: Failed notifications are captured for analysis
- 📊 **Monitoring**: CloudWatch metrics for queue depth and processing times

### Notification Types
- **Email Notifications**:
  - Appointment confirmations and updates
  - Order status changes
  - Payment confirmations
  - Report ready notifications
  - Invoice delivery
- **WebSocket Notifications**:
  - Real-time order updates
  - Live chat messages
  - Staff assignment changes
  - System status updates

## 🔧 Configuration

### Environment Variables

The deployment automatically configures environment variables for:
- DynamoDB table names
- WebSocket API endpoints
- S3 bucket names

### Customization

You can customize the deployment by modifying:
- `deploy.sh`: Main deployment configuration
- `infrastructure/*.yaml`: CloudFormation templates
- Lambda function code in `lambda/` directories

## 🚀 Deployment Options

### 🏗️ **CI/CD Deployment (Recommended)**

The project includes comprehensive GitHub Actions workflows for automated deployment:

#### **Branch-Based Deployment**
- **`dev` branch** → Automatically deploys to development environment
- **`prod` branch** → Automatically deploys to production environment

#### **Setup CI/CD**
1. **Configure GitHub Secrets** (see [.github/SECRETS.md](.github/SECRETS.md)):
   ```
   AWS_ACCESS_KEY_ID          # Development AWS credentials
   AWS_SECRET_ACCESS_KEY      # Development AWS credentials
   PROD_AWS_ACCESS_KEY_ID     # Production AWS credentials
   PROD_AWS_SECRET_ACCESS_KEY # Production AWS credentials
   ```

2. **Push to deploy**:
   ```bash
   # Deploy to development
   git push origin dev
   
   # Deploy to production
   git push origin prod
   ```

3. **Monitor deployments** in GitHub Actions tab

#### **Available Workflows**
- 🔄 **Auto Deploy Dev**: Validates, deploys, and tests development
- 🚀 **Auto Deploy Prod**: Security scan, deploy, and health check production
- ⚡ **Update Lambdas**: Fast Lambda-only updates (manual trigger)
- 🧹 **Cleanup**: Remove environment resources (manual trigger)

📖 **Full CI/CD Documentation**: [.github/CI-CD.md](.github/CI-CD.md)

### 🛠️ **Local Deployment**

For local development and testing:

#### **Quick Lambda Updates**

For rapid development when only Lambda code changes:

```bash
# Update all Lambda functions
./update-lambdas.sh --all

# Update specific functions
./update-lambdas.sh api-get-prices api-create-order

# List available functions
./update-lambdas.sh --list
```

#### **Development Workflow**

1. **Make code changes** in `lambda/` directories
2. **Quick update** specific functions:
   ```bash
   ./update-lambdas.sh api-get-prices
   ```
3. **Test immediately** using:
   ```bash
   ./dev-tools.sh test api-get-prices
   ./dev-tools.sh logs api-get-prices
   ```

#### Local Development

1. **Install dependencies** for individual Lambda functions:
   ```bash
   cd lambda/api-get-prices
   pip install -r requirements.txt
   ```

2. **Test functions locally** using AWS SAM or similar tools

3. **Quick redeploy after changes**:
   ```bash
   ./update-lambdas.sh api-get-prices
   ```

4. **Full redeploy** (only when infrastructure changes):
   ```bash
   ./deploy.sh
   ```

#### Adding New Features

1. **Create new Lambda function** in `lambda/` directory
2. **Add to CloudFormation template** in `infrastructure/lambda-functions.yaml`
3. **Add API Gateway integration** in `infrastructure/api-gateway.yaml`
4. **Redeploy** using `./deploy.sh`

## 🗑️ Cleanup

To remove all deployed resources:

```bash
./cleanup.sh
```

⚠️ **Warning**: This will permanently delete all data and resources.

## 📈 Monitoring & Logging

- **CloudWatch Logs**: All Lambda functions log to CloudWatch
- **API Gateway Logs**: Request/response logging enabled
- **CloudTrail**: API calls are logged for audit purposes

## 🔒 Security

- **IAM Roles**: Least privilege access for all services
- **VPC**: Can be configured for enhanced security
- **Encryption**: Data encrypted at rest and in transit
- **Auth0**: JWT-based authentication with role validation

## 📞 Support

For issues or questions:
1. Check CloudWatch logs for error details
2. Verify AWS permissions
3. Ensure all prerequisites are met
4. Check the deployment outputs for configuration details

## 📝 License

This project is proprietary to Auto Lab Solutions.

---

## 📚 **Script Reference**

| Script | Purpose | Usage |
|--------|---------|-------|
| `deploy.sh` | Full infrastructure deployment | `./deploy.sh` |
| `update-lambdas.sh` | Update Lambda functions only | `./update-lambdas.sh --all` |
| `update-websocket-endpoints.sh` | Update WebSocket endpoints | `./update-websocket-endpoints.sh` |
| `dev-tools.sh` | Development and debugging tools | `./dev-tools.sh status` |
| `validate-deployment.sh` | Validate deployment success | `./validate-deployment.sh` |
| `validate-notification-system.sh` | Validate notification system | `./validate-notification-system.sh` |
| `upload-templates.sh` | Upload CloudFormation templates | `./upload-templates.sh` |
| `cleanup.sh` | Remove all resources | `./cleanup.sh` |

## 🚀 **Development Workflow**

### **Initial Setup**
```bash
./deploy.sh                    # Deploy entire infrastructure (first time)
./validate-deployment.sh       # Verify everything works
```

### **Daily Development**
```bash
# Make changes to Lambda code
./update-lambdas.sh api-get-prices     # Update specific function (seconds)
./dev-tools.sh test api-get-prices     # Test the function
./dev-tools.sh logs api-get-prices     # Check logs
```

### **Infrastructure Changes**
```bash
./deploy.sh                    # Only when changing CloudFormation templates
```

### **Cleanup**
```bash
./cleanup.sh                  # Remove everything when done
```

**Deployment Status**: Ready for production ✅

## 🌍 **Multi-Environment Workflow**

### **Development Environment**

Recommended for development, testing, and staging:

```bash
# 1. Set development as default
./config/environments.sh set development

# 2. Deploy to development
./deploy.sh --env development

# 3. Test your changes
./dev-tools.sh --env dev status
./dev-tools.sh --env dev test api-get-users

# 4. Update specific functions during development
./update-lambdas.sh --env dev api-get-prices api-get-users

# 5. View logs for debugging
./dev-tools.sh --env dev logs api-get-prices
```

### **Production Environment**

For production deployments:

```bash
# 1. Validate development environment first
./validate-deployment.sh --env development

# 2. Deploy to production
./deploy.sh --env production

# 3. Validate production deployment
./validate-deployment.sh --env production

# 4. Monitor production resources
./dev-tools.sh --env production status
./dev-tools.sh --env production endpoints
```

### **Environment Management**

```bash
# View available environments
./config/environments.sh list

# Show current environment configuration
./config/environments.sh show

# Show specific environment configuration
./config/environments.sh show production

# Switch default environment
./config/environments.sh set production
```

### **Recommended Workflow**

1. **Initial Setup**: Deploy development environment first
2. **Development**: Use development for testing and iteration
3. **Testing**: Validate development environment before production
4. **Production**: Deploy to production only after thorough testing
5. **Monitoring**: Use dev-tools to monitor both environments
## 🚀 **CI/CD Workflow Examples**

### **Development Workflow**
```bash
# 1. Create feature branch
git checkout -b feature/new-api-endpoint

# 2. Make changes to Lambda functions or infrastructure
# Edit lambda/api-get-prices/main.py

# 3. Commit and push to dev branch
git add .
git commit -m "Add new pricing calculation logic"
git push origin dev

# 4. GitHub Actions automatically:
#    - Validates Python syntax
#    - Validates CloudFormation templates  
#    - Deploys to development environment
#    - Runs integration tests
#    - Reports status

# 5. Test in development environment
# Check GitHub Actions logs or use local tools:
./dev-tools.sh --env development status
./dev-tools.sh --env development test api-get-prices
```

### **Production Deployment**
```bash
# 1. After testing in development, create PR to prod
git checkout prod
git pull origin prod
git merge dev
git push origin prod

# 2. GitHub Actions automatically:
#    - Runs security scans (Bandit, Safety)
#    - Creates backup of current state
#    - Deploys to production environment
#    - Performs health checks
#    - Sends notifications

# 3. Monitor production deployment
# Check GitHub Actions logs for status
```

### **Lambda-Only Updates** 
```bash
# Via GitHub Actions UI:
# 1. Go to repository → Actions tab
# 2. Click "Update Lambda Functions" workflow
# 3. Click "Run workflow"
# 4. Select:
#    - Environment: development or production
#    - Functions: "all" or "api-get-prices,api-get-users"
# 5. Click "Run workflow"

# This provides:
# ⚡ 10x faster than full deployment
# 🎯 Update specific functions only
# ✅ Automatic validation and testing
# 🔄 No infrastructure changes
```

### **Environment Cleanup**
```bash
# Via GitHub Actions UI:
# 1. Go to repository → Actions tab
# 2. Click "Cleanup Environment" workflow  
# 3. Click "Run workflow"
# 4. Select environment and type "DELETE" to confirm
# 5. Click "Run workflow"

# Features:
# 🛡️ Confirmation required
# 💾 Automatic backup before cleanup
# 🧹 Complete resource removal
# 📊 Verification report
```


