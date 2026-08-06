from urllib.parse import (
    parse_qsl,
    urlencode,
    urlsplit,
    urlunsplit,
)

TRACKING_QUERY_KEYS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
}


def _is_tracking_parameter(name: str) -> bool:
    """Return whether a query parameter is used for tracking."""

    normalized_name = name.casefold()

    return normalized_name.startswith("utm_") or normalized_name in TRACKING_QUERY_KEYS


def normalize_url(value: str) -> str:
    """Return a canonical HTTP or HTTPS URL."""

    raw_url = value.strip()

    if not raw_url:
        raise ValueError("URL must not be empty.")

    parsed = urlsplit(raw_url)
    scheme = parsed.scheme.casefold()

    if scheme not in {"http", "https"}:
        raise ValueError("URL scheme must be HTTP or HTTPS.")

    hostname = parsed.hostname

    if not hostname:
        raise ValueError("URL must include a hostname.")

    if parsed.username is not None or parsed.password is not None:
        raise ValueError("URL must not include credentials.")

    try:
        port = parsed.port
    except ValueError as error:
        raise ValueError("URL contains an invalid port.") from error

    normalized_hostname = hostname.casefold().rstrip(".")
    netloc_hostname = (
        f"[{normalized_hostname}]" if ":" in normalized_hostname else normalized_hostname
    )

    is_default_port = (scheme == "http" and port == 80) or (scheme == "https" and port == 443)

    if port is not None and not is_default_port:
        netloc = f"{netloc_hostname}:{port}"
    else:
        netloc = netloc_hostname

    path = parsed.path or "/"

    if path != "/":
        path = path.rstrip("/") or "/"

    query_parameters = [
        (name, parameter_value)
        for name, parameter_value in parse_qsl(
            parsed.query,
            keep_blank_values=True,
        )
        if not _is_tracking_parameter(name)
    ]
    query_parameters.sort()

    normalized_query = urlencode(
        query_parameters,
        doseq=True,
    )

    return urlunsplit(
        (
            scheme,
            netloc,
            path,
            normalized_query,
            "",
        )
    )
