#!/usr/bin/env bash

set -euo pipefail

repository_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
terraform_directory="${repository_root}/infra/terraform/staging"
backend_configuration=${TF_BACKEND_CONFIG:-"${repository_root}/infra/terraform/bootstrap/backend.hcl"}
image_tag=${IMAGE_TAG:-$(git -C "${repository_root}" rev-parse --short=12 HEAD)}
desired_count=${APPLICATION_DESIRED_COUNT:-1}

required_commands=(aws curl docker git jq terraform)
for command_name in "${required_commands[@]}"; do
  if ! command -v "${command_name}" >/dev/null 2>&1; then
    echo "Required command is unavailable: ${command_name}" >&2
    exit 1
  fi
done

if [[ ! -f "${backend_configuration}" ]]; then
  echo "Terraform backend configuration not found: ${backend_configuration}" >&2
  exit 1
fi

if [[ "${desired_count}" != "1" && "${desired_count}" != "2" ]]; then
  echo "APPLICATION_DESIRED_COUNT must be 1 or 2 for deployment." >&2
  exit 1
fi

terraform -chdir="${terraform_directory}" init \
  -backend-config="${backend_configuration}" \
  -input=false

apply_arguments=(
  -input=false
  -var="api_image_tag=${image_tag}"
  -var="frontend_image_tag=${image_tag}"
)
if [[ "${AWS_DEPLOY_AUTO_APPROVE:-false}" == "true" ]]; then
  apply_arguments+=(-auto-approve)
fi

echo "Creating or reconciling dependencies with zero running application tasks."
terraform -chdir="${terraform_directory}" apply \
  "${apply_arguments[@]}" \
  -var="application_desired_count=0"

provider_secret_arn=$(terraform -chdir="${terraform_directory}" output -raw provider_secret_arn)

if [[ -n "${ANTHROPIC_API_KEY:-}" || -n "${TAVILY_API_KEY:-}" || -n "${MILVUS_TOKEN:-}" ]]; then
  if [[ -z "${ANTHROPIC_API_KEY:-}" || -z "${TAVILY_API_KEY:-}" || -z "${MILVUS_TOKEN:-}" ]]; then
    echo "ANTHROPIC_API_KEY, TAVILY_API_KEY, and MILVUS_TOKEN must be supplied together." >&2
    exit 1
  fi

  provider_secret_json=$(jq -cn \
    --arg anthropic "${ANTHROPIC_API_KEY}" \
    --arg tavily "${TAVILY_API_KEY}" \
    --arg milvus "${MILVUS_TOKEN}" \
    '{ANTHROPIC_API_KEY:$anthropic,TAVILY_API_KEY:$tavily,MILVUS_TOKEN:$milvus}')
  aws secretsmanager put-secret-value \
    --secret-id "${provider_secret_arn}" \
    --secret-string "${provider_secret_json}" \
    >/dev/null
else
  provider_secret_json=$(aws secretsmanager get-secret-value \
    --secret-id "${provider_secret_arn}" \
    --query SecretString \
    --output text)
  if ! jq -e '
    .ANTHROPIC_API_KEY != "replace-after-apply" and
    .TAVILY_API_KEY != "replace-after-apply" and
    .MILVUS_TOKEN != "replace-after-apply" and
    ([.ANTHROPIC_API_KEY, .TAVILY_API_KEY, .MILVUS_TOKEN] | all(length > 0))
  ' >/dev/null <<<"${provider_secret_json}"; then
    echo "Provider secret still contains placeholders; update it before deployment." >&2
    exit 1
  fi
fi
unset provider_secret_json

api_repository=$(terraform -chdir="${terraform_directory}" output -raw api_repository_url)
frontend_repository=$(terraform -chdir="${terraform_directory}" output -raw frontend_repository_url)
registry_host=${api_repository%%/*}

aws ecr get-login-password |
  docker login --username AWS --password-stdin "${registry_host}"

docker buildx build \
  --platform linux/arm64 \
  --provenance=false \
  --tag "${api_repository}:${image_tag}" \
  --push \
  "${repository_root}"

docker buildx build \
  --platform linux/arm64 \
  --provenance=false \
  --build-arg VITE_ENABLED_LLM_PROVIDERS=claude \
  --tag "${frontend_repository}:${image_tag}" \
  --push \
  "${repository_root}/frontend"

echo "Starting ${desired_count} application task(s) with immutable tag ${image_tag}."
terraform -chdir="${terraform_directory}" apply \
  "${apply_arguments[@]}" \
  -var="application_desired_count=${desired_count}"

cluster_name=$(terraform -chdir="${terraform_directory}" output -raw ecs_cluster_name)
service_name=$(terraform -chdir="${terraform_directory}" output -raw ecs_service_name)
distribution_id=$(terraform -chdir="${terraform_directory}" output -raw cloudfront_distribution_id)
application_url=$(terraform -chdir="${terraform_directory}" output -raw application_url)

aws ecs wait services-stable \
  --cluster "${cluster_name}" \
  --services "${service_name}"

aws cloudfront create-invalidation \
  --distribution-id "${distribution_id}" \
  --paths "/*" \
  >/dev/null

curl --fail --silent --show-error \
  --retry 12 \
  --retry-all-errors \
  --retry-delay 10 \
  "${application_url}/api/health" \
  >/dev/null

echo "AWS staging deployment is healthy: ${application_url}"
