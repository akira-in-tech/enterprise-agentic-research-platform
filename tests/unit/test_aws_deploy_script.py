import os
import subprocess
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).parents[2]
DEPLOY_SCRIPT = REPOSITORY_ROOT / "scripts" / "aws-deploy.sh"
REQUIRED_ENVIRONMENT_VARIABLES = (
    "TF_VAR_budget_notification_email",
    "TF_VAR_anthropic_model",
    "TF_VAR_milvus_uri",
    "ANTHROPIC_API_KEY",
    "TAVILY_API_KEY",
    "MILVUS_TOKEN",
)


def run_deploy_preflight(
    overrides: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    for variable_name in REQUIRED_ENVIRONMENT_VARIABLES:
        environment.pop(variable_name, None)
    environment.update(overrides or {})

    return subprocess.run(
        ["bash", str(DEPLOY_SCRIPT)],
        cwd=REPOSITORY_ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )


def complete_environment() -> dict[str, str]:
    return {
        "TF_VAR_budget_notification_email": "owner@example.com",
        "TF_VAR_anthropic_model": "supported-model-id",
        "TF_VAR_milvus_uri": "https://milvus.example.com",
        "ANTHROPIC_API_KEY": "test-anthropic-secret",
        "TAVILY_API_KEY": "test-tavily-secret",
        "MILVUS_TOKEN": "test-milvus-secret",
    }


def test_deploy_preflight_rejects_missing_environment_variables() -> None:
    result = run_deploy_preflight()

    assert result.returncode == 1
    assert "Missing required deployment environment variables" in result.stderr
    for variable_name in REQUIRED_ENVIRONMENT_VARIABLES:
        assert variable_name in result.stderr


def test_deploy_preflight_rejects_placeholder_anthropic_model() -> None:
    environment = complete_environment()
    environment["TF_VAR_anthropic_model"] = "replace-with-supported-model-id"

    result = run_deploy_preflight(environment)

    assert result.returncode == 1
    assert "must name a supported deployed model" in result.stderr
    assert "test-anthropic-secret" not in result.stderr


def test_deploy_preflight_rejects_placeholder_milvus_endpoint() -> None:
    environment = complete_environment()
    environment["TF_VAR_milvus_uri"] = "https://replace-with-managed-milvus-endpoint"

    result = run_deploy_preflight(environment)

    assert result.returncode == 1
    assert "must be a real managed HTTPS endpoint" in result.stderr
    assert "test-milvus-secret" not in result.stderr
