from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import delete

from app.core.config import settings
from app.db.models import Tenant
from app.db.repositories import TenantRepository
from app.db.session import create_database_engine, create_session_factory
from app.services.embeddings.deterministic import DeterministicEmbeddingClient
from app.services.knowledge import KnowledgeDocumentService, PostgresKnowledgeDocumentStore
from app.services.knowledge.indexing import KnowledgeIndexer
from app.services.knowledge.retrieval import PrivateKnowledgeRetriever
from app.services.storage import LocalDocumentStorage
from app.services.vector_store.memory import InMemoryVectorStore


@pytest.mark.integration
@pytest.mark.anyio
async def test_private_document_upload_retrieval_and_delete_live(
    tmp_path: Path,
) -> None:
    """Verify the complete durable private-document lifecycle."""

    if not settings.run_live_tests:
        pytest.skip("Set RUN_LIVE_TESTS=true to run external integration tests.")

    engine = create_database_engine(echo=False)
    session_factory = create_session_factory(engine)
    tenant_id = None
    vector_store = InMemoryVectorStore(dimensions=16)

    try:
        async with session_factory.begin() as session:
            tenant = await TenantRepository(session).create(
                slug=f"private-knowledge-{uuid4().hex[:12]}",
                name="Private Knowledge Verification",
            )
            tenant_id = tenant.id

        embedding_client = DeterministicEmbeddingClient(dimensions=16)
        service = KnowledgeDocumentService(
            PostgresKnowledgeDocumentStore(session_factory),
            LocalDocumentStorage(tmp_path),
            KnowledgeIndexer(
                embedding_client,
                vector_store,
                max_words=20,
                overlap_words=2,
            ),
            vector_store,
        )

        created = await service.upload(
            tenant_id=tenant_id,
            uploaded_by_user_id=None,
            filename="incident-response.md",
            declared_media_type="text/markdown",
            raw_content=(
                b"The Atlas service uses a transactional outbox to publish "
                b"durable incident events after PostgreSQL commits."
            ),
        )

        assert created.status == "ready"
        assert list(tmp_path.rglob("source.md"))

        stored = await service.get(
            tenant_id=tenant_id,
            document_id=created.id,
        )
        assert stored is not None
        assert stored.filename == "incident-response.md"

        sources = await PrivateKnowledgeRetriever(
            embedding_client,
            vector_store,
        ).retrieve(
            tenant_id=str(tenant_id),
            query="How does Atlas publish durable incident events?",
            limit=3,
        )
        assert sources
        assert "transactional outbox" in sources[0].content

        assert await service.delete(
            tenant_id=tenant_id,
            document_id=created.id,
        )
        assert (
            await service.get(
                tenant_id=tenant_id,
                document_id=created.id,
            )
            is None
        )
        assert list(tmp_path.rglob("source.md")) == []
        assert (
            await vector_store.search(
                tenant_id=str(tenant_id),
                query_vector=(1.0,) * 16,
            )
            == []
        )
    finally:
        if tenant_id is not None:
            async with session_factory.begin() as session:
                await session.execute(delete(Tenant).where(Tenant.id == tenant_id))

        await vector_store.close()
        await engine.dispose()
