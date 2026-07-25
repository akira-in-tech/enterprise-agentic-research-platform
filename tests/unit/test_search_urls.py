import pytest

from app.services.search.urls import normalize_url


def test_normalize_url_removes_tracking_and_fragment() -> None:
    result = normalize_url(
        "HTTPS://Example.COM:443/docs/"
        "?utm_source=newsletter&b=2&a=1"
        "#installation"
    )

    assert result == (
        "https://example.com/docs?a=1&b=2"
    )


def test_normalize_url_preserves_non_default_port() -> None:
    result = normalize_url(
        "http://Example.COM:8080/api/?page=2"
    )

    assert result == (
        "http://example.com:8080/api?page=2"
    )


@pytest.mark.parametrize(
    "url",
    [
        "",
        "example.com/docs",
        "ftp://example.com/file",
        "https://user:password@example.com/docs",
    ],
)
def test_normalize_url_rejects_unsupported_urls(
    url: str,
) -> None:
    with pytest.raises(ValueError):
        normalize_url(url)