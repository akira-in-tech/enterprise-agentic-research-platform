# GitHub OIDC Deployment Identity

This Terraform root creates the account-level GitHub Actions OIDC provider and
the staging deployment role. It is intentionally separate from disposable
staging resources so routine staging destruction cannot remove CI identity.

The trust policy accepts only tokens whose audience is `sts.amazonaws.com` and
whose immutable subject identifies this repository's protected `staging`
environment. The deployment role uses one-hour sessions, exact Terraform state
object paths, region-constrained infrastructure actions, exact ECR repository
and ECS role names, and an `iam:PassRole` condition restricted to ECS tasks.
It has no long-lived AWS access key and no permission to read provider secret
values.

Current verification status:

- `terraform validate`: passed
- mock-provider contract test: 1 passed
- authenticated account plan: 5 add, 0 change, 0 destroy
- inline-policy aggregate: 8,954 characters of the 10,240-character role quota
- every planned IAM action matched the AWS Service Authorization Reference
- IAM Access Analyzer: zero findings across the bootstrap and deploy policies
- AWS apply: 5 added, 0 changed, 0 destroyed
- AWS API readback: issuer, audience, trust, role session, tags, and policies verified
- remote state: AES256 encrypted, versioned, and limited to the identity prefix
- post-apply plan: no changes

Initialize and plan without applying:

```bash
cp infra/terraform/identity/backend.hcl.example \
  infra/terraform/identity/backend.hcl

terraform -chdir=infra/terraform/identity init \
  -backend-config=backend.hcl
terraform -chdir=infra/terraform/identity validate
terraform -chdir=infra/terraform/identity plan
```

Creating or changing IAM resources requires a separately reviewed bootstrap
identity. Do not attach `AdministratorAccess`, create IAM user access keys, or
weaken the repository/environment conditions to make a failed OIDC assumption
work.
