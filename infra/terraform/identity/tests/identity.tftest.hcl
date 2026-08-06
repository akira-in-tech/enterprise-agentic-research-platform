mock_provider "aws" {}

override_data {
  target = data.aws_caller_identity.current
  values = {
    account_id = "123456789012"
    arn        = "arn:aws:iam::123456789012:user/test"
    id         = "123456789012"
    user_id    = "test"
  }
}

override_resource {
  target          = aws_iam_openid_connect_provider.github
  override_during = plan
  values = {
    arn = "arn:aws:iam::123456789012:oidc-provider/token.actions.githubusercontent.com"
  }
}

run "identity_contract" {
  command = plan

  assert {
    condition = (
      aws_iam_openid_connect_provider.github.url == "https://token.actions.githubusercontent.com" &&
      aws_iam_openid_connect_provider.github.client_id_list == toset(["sts.amazonaws.com"])
    )
    error_message = "GitHub OIDC must use the official issuer and STS audience."
  }

  assert {
    condition = (
      jsondecode(aws_iam_role.github_deploy.assume_role_policy).Statement[0].Condition.StringEquals["token.actions.githubusercontent.com:aud"] == "sts.amazonaws.com" &&
      jsondecode(aws_iam_role.github_deploy.assume_role_policy).Statement[0].Condition.StringEquals["token.actions.githubusercontent.com:sub"] == "repo:akira-in-tech@109833555/enterprise-agentic-research-platform@1325166723:environment:staging"
    )
    error_message = "OIDC trust must match the immutable repository identity and staging environment."
  }

  assert {
    condition     = aws_iam_role.github_deploy.max_session_duration == 3600
    error_message = "GitHub deployment sessions must be limited to one hour."
  }

  assert {
    condition = (
      jsondecode(aws_iam_role_policy.global_staging.policy).Statement[4].Action == "iam:PassRole" &&
      jsondecode(aws_iam_role_policy.global_staging.policy).Statement[4].Condition.StringEquals["iam:PassedToService"] == "ecs-tasks.amazonaws.com" &&
      length(jsondecode(aws_iam_role_policy.global_staging.policy).Statement[4].Resource) == 2
    )
    error_message = "PassRole must be limited to the two project roles and ECS tasks."
  }

  assert {
    condition = !strcontains(
      aws_iam_role_policy.regional_staging.policy,
      "secretsmanager:GetSecretValue",
    )
    error_message = "The GitHub deployment role must not read provider secret values."
  }
}
