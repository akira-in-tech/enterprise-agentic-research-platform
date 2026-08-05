from sqlalchemy import CheckConstraint

from app.db.models import metadata


def test_tenant_table_has_named_business_constraints() -> None:
    tenant_table = metadata.tables["tenants"]

    constraint_names = {str(constraint.name) for constraint in tenant_table.constraints}

    assert {
        "pk_tenants",
        "uq_tenants_slug",
        "ck_tenants_slug_not_blank",
        "ck_tenants_name_not_blank",
    } <= constraint_names


def test_user_table_enforces_tenant_membership() -> None:
    user_table = metadata.tables["users"]

    constraint_names = {str(constraint.name) for constraint in user_table.constraints}

    assert {
        "pk_users",
        "uq_users_tenant_id_id",
        "uq_users_tenant_id_email",
        "ck_users_email_not_blank",
        "fk_users_tenant_id_tenants",
    } <= constraint_names

    foreign_key = next(iter(user_table.foreign_key_constraints))

    assert foreign_key.ondelete == "CASCADE"
    assert {element.target_fullname for element in foreign_key.elements} == {
        "tenants.id",
    }


def test_research_run_has_valid_lifecycle_constraints() -> None:
    research_run_table = metadata.tables["research_runs"]

    check_constraint_names = {
        str(constraint.name)
        for constraint in research_run_table.constraints
        if isinstance(
            constraint,
            CheckConstraint,
        )
    }

    assert check_constraint_names == {
        "ck_research_runs_query_not_blank",
        "ck_research_runs_status_valid",
        "ck_research_runs_llm_provider_valid",
        "ck_research_runs_route_valid",
    }

    assert research_run_table.c.requested_by_user_id.nullable is True
    assert research_run_table.c.status.server_default is not None
    status_constraint = next(
        constraint
        for constraint in research_run_table.constraints
        if constraint.name == "ck_research_runs_status_valid"
    )
    assert isinstance(status_constraint, CheckConstraint)
    assert "cancelled" in str(status_constraint.sqltext)


def test_research_run_enforces_tenant_scoped_user_reference() -> None:
    research_run_table = metadata.tables["research_runs"]

    foreign_keys = {
        str(constraint.name): constraint
        for constraint in research_run_table.foreign_key_constraints
    }

    assert set(foreign_keys) == {
        "fk_research_runs_tenant_id_tenants",
        "fk_research_runs_tenant_user",
    }

    tenant_user_foreign_key = foreign_keys["fk_research_runs_tenant_user"]

    assert {element.target_fullname for element in tenant_user_foreign_key.elements} == {
        "users.tenant_id",
        "users.id",
    }
    assert tenant_user_foreign_key.ondelete == "NO ACTION"


def test_research_run_has_tenant_query_indexes() -> None:
    research_run_table = metadata.tables["research_runs"]

    assert {index.name for index in research_run_table.indexes} == {
        "ix_research_runs_tenant_created_at",
        "ix_research_runs_tenant_status",
    }


def test_research_report_is_bound_to_one_tenant_scoped_run() -> None:
    report_table = metadata.tables["research_reports"]
    constraint_names = {str(constraint.name) for constraint in report_table.constraints}

    assert {
        "pk_research_reports",
        "fk_research_reports_tenant_run",
        "uq_research_reports_research_run_id",
    } <= constraint_names

    foreign_key = next(iter(report_table.foreign_key_constraints))

    assert foreign_key.ondelete == "CASCADE"
    assert {element.target_fullname for element in foreign_key.elements} == {
        "research_runs.tenant_id",
        "research_runs.id",
    }


def test_research_source_is_unique_within_report() -> None:
    source_table = metadata.tables["research_sources"]
    constraint_names = {str(constraint.name) for constraint in source_table.constraints}

    assert {
        "pk_research_sources",
        "fk_research_sources_report_id_research_reports",
        "uq_research_sources_report_source",
    } <= constraint_names
    assert {index.name for index in source_table.indexes} == {"ix_research_sources_tenant_run"}


def test_knowledge_document_enforces_tenant_and_lifecycle_constraints() -> None:
    document_table = metadata.tables["knowledge_documents"]
    constraint_names = {str(constraint.name) for constraint in document_table.constraints}

    assert {
        "pk_knowledge_documents",
        "fk_knowledge_documents_tenant_id_tenants",
        "fk_knowledge_documents_tenant_user",
        "uq_knowledge_documents_tenant_id_id",
        "uq_knowledge_documents_tenant_content_sha256",
        "uq_knowledge_documents_tenant_vector_document_id",
        "ck_knowledge_documents_filename_not_blank",
        "ck_knowledge_documents_media_type_valid",
        "ck_knowledge_documents_byte_size_positive",
        "ck_knowledge_documents_content_sha256_valid",
        "ck_knowledge_documents_storage_key_not_blank",
        "ck_knowledge_documents_status_valid",
        "ck_knowledge_documents_error_state_valid",
        "ck_knowledge_documents_indexed_state_valid",
    } <= constraint_names
    assert {index.name for index in document_table.indexes} == {
        "ix_knowledge_documents_tenant_created_at",
        "ix_knowledge_documents_tenant_status",
    }

    foreign_keys = {
        str(constraint.name): constraint for constraint in document_table.foreign_key_constraints
    }
    assert foreign_keys["fk_knowledge_documents_tenant_id_tenants"].ondelete == "CASCADE"
    assert {
        element.target_fullname
        for element in foreign_keys["fk_knowledge_documents_tenant_user"].elements
    } == {
        "users.tenant_id",
        "users.id",
    }
