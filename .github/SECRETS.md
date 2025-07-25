# GitHub Secrets Configuration

This document outlines the GitHub secrets required for the CI/CD workflows.

## Required Secrets

### Development Environment Secrets
Configure these secrets in your GitHub repository settings:

- `AWS_ACCESS_KEY_ID`: AWS Access Key ID for development deployments
- `AWS_SECRET_ACCESS_KEY`: AWS Secret Access Key for development deployments

### Production Environment Secrets
Configure these secrets in your GitHub repository settings:

- `PROD_AWS_ACCESS_KEY_ID`: AWS Access Key ID for production deployments  
- `PROD_AWS_SECRET_ACCESS_KEY`: AWS Secret Access Key for production deployments

## AWS IAM Permissions

The AWS credentials must have the following permissions:

### Core Services
- CloudFormation: Full access
- Lambda: Full access
- API Gateway: Full access
- DynamoDB: Full access
- S3: Full access
- CloudFront: Full access
- IAM: CreateRole, AttachRolePolicy, CreatePolicy

### Recommended IAM Policy

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "cloudformation:*",
                "lambda:*",
                "apigateway:*",
                "dynamodb:*",
                "s3:*",
                "cloudfront:*",
                "iam:CreateRole",
                "iam:AttachRolePolicy",
                "iam:CreatePolicy",
                "iam:PassRole",
                "iam:GetRole",
                "iam:GetPolicy",
                "iam:ListRoles",
                "iam:ListPolicies",
                "logs:*"
            ],
            "Resource": "*"
        }
    ]
}
```

## Environment Configuration

### GitHub Environments
It's recommended to set up GitHub Environments for additional security:

1. Go to Settings > Environments in your repository
2. Create environments: `development` and `production`
3. Configure protection rules for production:
   - Required reviewers
   - Wait timer
   - Deployment branches (restrict to `prod` branch)

### Branch Protection
Configure branch protection rules:

1. **dev branch**: 
   - Require pull request reviews
   - Require status checks to pass
   
2. **prod branch**:
   - Require pull request reviews (2+ reviewers recommended)
   - Require status checks to pass
   - Include administrators

## Workflow Triggers

### Automatic Deployments
- **Development**: Triggers on push to `dev` branch
- **Production**: Triggers on push to `prod` branch

### Manual Deployments
- **Lambda Updates**: Manual trigger via GitHub Actions UI
- **Cleanup**: Manual trigger with confirmation required

## Security Best Practices

1. **Separate AWS Accounts**: Use different AWS accounts for dev/prod
2. **Least Privilege**: Grant only necessary permissions
3. **Rotate Keys**: Regularly rotate AWS access keys
4. **Monitor Usage**: Set up CloudTrail and billing alerts
5. **Review Deployments**: Require code reviews before production

## Troubleshooting

### Common Issues

1. **Permission Denied**: Check IAM permissions and secret values
2. **Stack Already Exists**: Use cleanup workflow or manual deletion
3. **Template Validation Failed**: Check CloudFormation template syntax
4. **Lambda Package Too Large**: Check dependencies and package size

### Getting Help

- Check workflow logs in GitHub Actions tab
- Use dev-tools.sh for debugging deployed resources
- Validate templates locally before pushing
