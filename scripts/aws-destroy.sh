#!/usr/bin/env bash

set -euo pipefail

repository_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
terraform_directory="${repository_root}/infra/terraform/staging"
backend_configuration=${TF_BACKEND_CONFIG:-"${repository_root}/infra/terraform/bootstrap/backend.hcl"}

if [[ "${AWS_DESTROY_CONFIRM:-}" != "destroy-staging" ]]; then
  echo "Refusing to destroy AWS resources." >&2
  echo "Set AWS_DESTROY_CONFIRM=destroy-staging after reviewing the active AWS account and plan." >&2
  exit 1
fi

if [[ ! -f "${backend_configuration}" ]]; then
  echo "Terraform backend configuration not found: ${backend_configuration}" >&2
  exit 1
fi

terraform -chdir="${terraform_directory}" init \
  -backend-config="${backend_configuration}" \
  -input=false

terraform -chdir="${terraform_directory}" plan \
  -destroy \
  -out=destroy.tfplan

terraform -chdir="${terraform_directory}" apply destroy.tfplan

echo "Staging resources were destroyed. The separate Terraform state bucket remains protected."
