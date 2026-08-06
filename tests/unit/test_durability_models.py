from sqlalchemy import CheckConstraint
from sqlalchemy.dialects.postgresql import JSONB

from app.db.models import metadata


def constraint_names(table_name: str) -> set[str]:
    return {str(constraint.name) for constraint in metadata.tables[table_name].constraints}


def test_checkpoint_is_tenant_scoped_versioned_json_state() -> None:
    table = metadata.tables["research_checkpoints"]

    assert {
        "pk_research_checkpoints",
        "fk_research_checkpoints_tenant_run",
        "uq_research_checkpoints_tenant_run_sequence",
        "ck_research_checkpoints_sequence_non_negative",
        "ck_research_checkpoints_node_name_not_blank",
    } <= constraint_names("research_checkpoints")
    assert isinstance(table.c.state.type, JSONB)
    assert {index.name for index in table.indexes} == {
        "ix_research_checkpoints_tenant_run_created_at"
    }
    foreign_key = next(iter(table.foreign_key_constraints))
    assert foreign_key.ondelete == "CASCADE"
    assert {element.target_fullname for element in foreign_key.elements} == {
        "research_runs.tenant_id",
        "research_runs.id",
    }


def test_audit_event_is_append_only_tenant_run_history() -> None:
    table = metadata.tables["research_audit_events"]

    assert {
        "pk_research_audit_events",
        "fk_research_audit_events_tenant_run",
        "ck_research_audit_events_event_type_not_blank",
        "ck_research_audit_events_actor_type_valid",
    } <= constraint_names("research_audit_events")
    assert isinstance(table.c.details.type, JSONB)
    assert table.c.details.server_default is not None
    assert {index.name for index in table.indexes} == {
        "ix_research_audit_events_tenant_run_created_at"
    }


def test_worker_lease_has_exclusive_token_and_expiry_guards() -> None:
    table = metadata.tables["research_worker_leases"]
    check_names = {
        str(constraint.name)
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }

    assert check_names == {
        "ck_research_worker_leases_worker_id_not_blank",
        "ck_research_worker_leases_attempt_positive",
        "ck_research_worker_leases_expiry_after_heartbeat",
    }
    assert {
        "pk_research_worker_leases",
        "fk_research_worker_leases_tenant_run",
        "uq_research_worker_leases_lease_token",
    } <= constraint_names("research_worker_leases")
    assert {column.name for column in table.primary_key.columns} == {
        "tenant_id",
        "research_run_id",
    }
    assert {index.name for index in table.indexes} == {"ix_research_worker_leases_expires_at"}
