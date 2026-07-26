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
