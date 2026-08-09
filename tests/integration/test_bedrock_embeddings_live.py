import math

import pytest
from botocore.exceptions import (  # type: ignore[import-untyped]
    ClientError,
    EndpointConnectionError,
    NoCredentialsError,
)

from app.core.config import settings
from app.services.embeddings.base import (
    EmbeddingVector,
)
from app.services.embeddings.bedrock import (
    BedrockTitanEmbeddingClient,
)


@pytest.mark.integration
@pytest.mark.anyio
async def test_bedrock_live_embeddings_are_well_formed() -> None:
    if not settings.run_live_tests:
        pytest.skip("Set RUN_LIVE_TESTS=true to run external integration tests.")

    client = BedrockTitanEmbeddingClient()
    vectors: list[EmbeddingVector]

    try:
        try:
            vectors = await client.embed_texts(
                [
                    "Explain DNS recursive resolution.",
                    "Compare HTTP/2 and HTTP/3.",
                ]
            )
        except NoCredentialsError as error:
            pytest.fail(
                "No AWS credentials found. Configure the default credential "
                "chain (AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY, an AWS CLI "
                f"profile, or an IAM role) before running this test. Error: {error}.",
                pytrace=False,
            )
        except EndpointConnectionError as error:
            pytest.fail(
                "Could not reach the Bedrock Runtime endpoint. Confirm "
                f"AWS_REGION={settings.aws_region!r} supports Bedrock and "
                f"the network allows outbound HTTPS. Error: {error}.",
                pytrace=False,
            )
        except ClientError as error:
            error_code = error.response.get("Error", {}).get("Code", "Unknown")
            pytest.fail(
                f"Bedrock InvokeModel failed with {error_code!r}. If this is "
                "AccessDeniedException, request model access for "
                f"{settings.bedrock_embedding_model!r} in the Bedrock console "
                f"for region {settings.aws_region!r} first. Error: {error}.",
                pytrace=False,
            )
    finally:
        await client.close()

    assert len(vectors) == 2

    assert all(len(vector) == settings.bedrock_embedding_dimensions for vector in vectors)

    assert all(math.isfinite(value) for vector in vectors for value in vector)

    assert all(any(value != 0.0 for value in vector) for vector in vectors)

    assert vectors[0] != vectors[1]
