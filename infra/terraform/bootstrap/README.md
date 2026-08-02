# Terraform State Bootstrap

This stack creates the one shared AWS resource that intentionally outlives a
disposable staging environment: an encrypted, versioned, private S3 bucket for
Terraform state and native S3 lock files.

It does not create application compute, networking, databases, caches, public
IP addresses, or load balancers. Running `terraform plan` does not create or
charge for resources. Running `terraform apply` creates the S3 bucket, whose
storage and request usage are billed separately by AWS.

## Prerequisites

- Terraform 1.7 or later
- an AWS account and authenticated AWS CLI profile
- permission to read the caller identity and manage the state bucket

Do not put AWS credentials in `.tfvars`, backend configuration, or Git. Use an
AWS profile, environment-based short-lived credentials, or CI workload
identity.

## Create the state bucket

```bash
cd infra/terraform/bootstrap
cp terraform.tfvars.example terraform.tfvars
terraform init
terraform fmt -check
terraform validate
terraform plan -out bootstrap.tfplan
terraform apply bootstrap.tfplan
terraform output staging_backend_configuration
```

Copy `backend.hcl.example` to `backend.hcl`, replace the account ID in the
bucket name with the output value, and keep that local file outside Git. The
staging stack will initialize with:

```bash
terraform init -backend-config=../bootstrap/backend.hcl
```

The bucket blocks public access, rejects plaintext transport, encrypts objects,
and keeps object versions for state recovery. Native S3 locking is enabled by
the environment backend configuration; a DynamoDB lock table is deliberately
not created because that Terraform locking mechanism is deprecated.

The bucket has `prevent_destroy` enabled. Destroy staging resources from their
environment stack; do not destroy the state bucket as part of routine cleanup.
