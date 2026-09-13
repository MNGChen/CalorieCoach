"""Canonical evidence identifiers; tracking parameters are not separate evidence."""
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def canonical_url(url: str) -> str:
    parsed = urlsplit(url)
    query = sorted((key, value) for key, value in parse_qsl(parsed.query)
                   if not key.casefold().startswith("utm_") and key.casefold() not in {"fbclid", "gclid"})
    return urlunsplit((parsed.scheme.casefold(), parsed.netloc.casefold().removeprefix("www."),
                       parsed.path.rstrip("/"), urlencode(query), ""))


def source_host(url: str) -> str:
    return (urlsplit(url).hostname or "").casefold().removeprefix("www.")
