from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.db.models import ResearchRun, Tenant, User
from app.db.repositories import (
    ResearchRunRepository,
    ResearchRunTransitionError,
    TenantRepository,
    UserRepository,
)
from app.db.session import (
    create_database_engine,
    create_session_factory,
)


@pytest.mark.integration
@pytest.mark.anyio
async def test_postgres_repositories_live_round_trip() -> None:
    """Verify tenant isolation and lifecycle transitions."""

    if not settings.run_live_tests:
        pytest.skip("Set RUN_LIVE_TESTS=true to run external integration tests.")

    engine = create_database_engine(
        echo=False,
    )
    session_factory = create_session_factory(engine)
    tenant_ids: list[UUID] = []

    try:
        async with session_factory() as session:
            async with session.begin():
                tenant_repository = TenantRepository(session)
                user_repository = UserRepository(session)
                run_repository = ResearchRunRepository(session)

                unique_suffix = uuid4().hex[:12]

                tenant_a = await tenant_repository.create(
                    slug=f"acme-platform-{unique_suffix}",
                    name="ACME Platform Engineering",
                )
                tenant_b = await tenant_repository.create(
                    slug=f"cloud-platform-{unique_suffix}",
                    name="Cloud Platform Engineering",
                )

                tenant_ids.extend(
                    [
                        tenant_a.id,
                        tenant_b.id,
                    ]
                )

                user_a = await user_repository.create(
                    tenant_id=tenant_a.id,
                    email="engineer@acme.example",
                    password_hash="test-password-hash",
                    display_name="ACME Engineer",
                )
                user_b = await user_repository.create(
                    tenant_id=tenant_b.id,
                    email="engineer@cloud.example",
                    password_hash="test-password-hash",
                    display_name="Cloud Engineer",
                )

                run_a = await run_repository.create(
                    tenant_id=tenant_a.id,
                    requested_by_user_id=user_a.id,
                    query=("Compare PostgreSQL B-tree and GIN indexing strategies."),
                    llm_provider="ollama",
                )
                run_b = await run_repository.create(
                    tenant_id=tenant_b.id,
                    requested_by_user_id=user_b.id,
                    query=("Explain HTTP/2 stream multiplexing."),
                    llm_provider="anthropic",
                )

                tenant_a_id = tenant_a.id
                tenant_b_id = tenant_b.id
                user_b_id = user_b.id
                run_a_id = run_a.id
                run_b_id = run_b.id

        async with session_factory() as session:
            run_repository = ResearchRunRepository(session)

            stored_run_a = await run_repository.get_for_tenant(
                tenant_id=tenant_a_id,
                research_run_id=run_a_id,
            )

            assert stored_run_a is not None
            assert stored_run_a.llm_provider == "ollama"
            assert stored_run_a.status == "queued"
            assert stored_run_a.started_at is None
            assert stored_run_a.completed_at is None

            cross_tenant_result = await run_repository.get_for_tenant(
                tenant_id=tenant_b_id,
                research_run_id=run_a_id,
            )

            assert cross_tenant_result is None

            tenant_a_runs = await run_repository.list_recent_for_tenant(
                tenant_id=tenant_a_id,
            )
            tenant_b_runs = await run_repository.list_recent_for_tenant(
                tenant_id=tenant_b_id,
            )

            assert [research_run.id for research_run in tenant_a_runs] == [
                run_a_id,
            ]
            assert [research_run.id for research_run in tenant_b_runs] == [
                run_b_id,
            ]

        async with session_factory() as session:
            async with session.begin():
                run_repository = ResearchRunRepository(session)

                running_run = await run_repository.mark_running(
                    tenant_id=tenant_a_id,
                    research_run_id=run_a_id,
                )

                assert running_run.status == "running"
                assert running_run.started_at is not None
                assert running_run.completed_at is None
                assert running_run.error_message is None

        async with session_factory() as session:
            with pytest.raises(
                ResearchRunTransitionError,
                match="cannot transition to running",
            ):
                async with session.begin():
                    run_repository = ResearchRunRepository(session)

                    await run_repository.mark_running(
                        tenant_id=tenant_a_id,
                        research_run_id=run_a_id,
                    )

        async with session_factory() as session:
            with pytest.raises(
                ResearchRunTransitionError,
                match="cannot transition to completed",
            ):
                async with session.begin():
                    run_repository = ResearchRunRepository(session)

                    await run_repository.mark_completed(
                        tenant_id=tenant_b_id,
                        research_run_id=run_a_id,
                    )

        async with session_factory() as session:
            async with session.begin():
                run_repository = ResearchRunRepository(session)

                completed_run = await run_repository.mark_completed(
                    tenant_id=tenant_a_id,
                    research_run_id=run_a_id,
                )
                failed_run = await run_repository.mark_failed(
                    tenant_id=tenant_b_id,
                    research_run_id=run_b_id,
                    error_message=("  Tavily search provider timed out.  "),
                )

                assert completed_run.status == "completed"
                assert completed_run.started_at is not None
                assert completed_run.completed_at is not None
                assert completed_run.error_message is None

                assert failed_run.status == "failed"
                assert failed_run.started_at is None
                assert failed_run.completed_at is not None
                assert failed_run.error_message == ("Tavily search provider timed out.")

        async with session_factory() as session:
            run_repository = ResearchRunRepository(session)

            stored_completed_run = await run_repository.get_for_tenant(
                tenant_id=tenant_a_id,
                research_run_id=run_a_id,
            )
            stored_failed_run = await run_repository.get_for_tenant(
                tenant_id=tenant_b_id,
                research_run_id=run_b_id,
            )

            assert stored_completed_run is not None
            assert stored_completed_run.status == "completed"
            assert stored_completed_run.started_at is not None
            assert stored_completed_run.completed_at is not None

            assert stored_failed_run is not None
            assert stored_failed_run.status == "failed"
            assert stored_failed_run.error_message == ("Tavily search provider timed out.")

        async with session_factory() as session:
            with pytest.raises(IntegrityError):
                async with session.begin():
                    run_repository = ResearchRunRepository(session)

                    await run_repository.create(
                        tenant_id=tenant_a_id,
                        requested_by_user_id=user_b_id,
                        query=("Attempt a cross-tenant research run."),
                        llm_provider="ollama",
                    )

        async with session_factory() as session:
            run_repository = ResearchRunRepository(session)

            tenant_a_runs_after_rollback = await run_repository.list_recent_for_tenant(
                tenant_id=tenant_a_id,
            )

            assert [research_run.id for research_run in tenant_a_runs_after_rollback] == [
                run_a_id,
            ]
            assert tenant_a_runs_after_rollback[0].status == "completed"
    finally:
        if tenant_ids:
            async with session_factory() as session:
                async with session.begin():
                    await session.execute(
                        delete(ResearchRun).where(ResearchRun.tenant_id.in_(tenant_ids))
                    )
                    await session.execute(delete(User).where(User.tenant_id.in_(tenant_ids)))
                    await session.execute(delete(Tenant).where(Tenant.id.in_(tenant_ids)))

        await engine.dispose()
