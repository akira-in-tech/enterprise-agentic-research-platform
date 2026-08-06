from app.core.config import Settings, parse_cors_allowed_origins


def test_cors_allowed_origins_defaults_to_empty() -> None:
    config = Settings()

    assert config.cors_allowed_origins == ""
    assert parse_cors_allowed_origins(config.cors_allowed_origins) == []


def test_parse_cors_allowed_origins_splits_and_trims() -> None:
    origins = parse_cors_allowed_origins(
        " http://localhost:5173 , https://staging.example.com ,,",
    )

    assert origins == ["http://localhost:5173", "https://staging.example.com"]


def test_parse_cors_allowed_origins_drops_duplicates() -> None:
    origins = parse_cors_allowed_origins(
        "https://example.com,https://example.com,https://other.example.com",
    )

    assert origins == ["https://example.com", "https://other.example.com"]


def test_parse_cors_allowed_origins_handles_blank_input() -> None:
    assert parse_cors_allowed_origins("") == []
    assert parse_cors_allowed_origins("   ") == []
