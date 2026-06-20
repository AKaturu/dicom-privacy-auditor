"""Small HTTP safety primitives shared by external integrations."""

from __future__ import annotations

import ssl
import urllib.request
from http.client import HTTPMessage
from typing import Any
from urllib.parse import SplitResult, urlsplit


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Refuse redirects so credentials and provenance checks stay on the configured origin."""

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: HTTPMessage,
        newurl: str,
    ) -> None:
        return None


def validate_http_url(
    url: str,
    *,
    require_https: bool = False,
    allow_query: bool = True,
    allow_fragment: bool = False,
) -> SplitResult:
    """Validate an absolute HTTP(S) URL and reject embedded credentials/control characters."""

    if not isinstance(url, str) or not url.strip():
        raise ValueError("URL must be a non-empty string")
    if url != url.strip() or any(ord(character) < 32 for character in url):
        raise ValueError("URL contains whitespace or control characters")
    parsed = urlsplit(url)
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        raise ValueError("URL must use http:// or https://")
    if require_https and scheme != "https":
        raise ValueError("URL must use HTTPS")
    if not parsed.hostname:
        raise ValueError("URL must include a hostname")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("URL must not embed credentials")
    try:
        _ = parsed.port
    except ValueError as exc:
        raise ValueError(f"URL has an invalid port: {exc}") from exc
    if parsed.query and not allow_query:
        raise ValueError("URL must not include a query string")
    if parsed.fragment and not allow_fragment:
        raise ValueError("URL must not include a fragment")
    return parsed


def build_no_redirect_opener(
    context: ssl.SSLContext | None = None,
) -> urllib.request.OpenerDirector:
    """Build a urllib opener that never follows redirects."""

    handlers: list[urllib.request.BaseHandler] = [NoRedirectHandler()]
    if context is not None:
        handlers.append(urllib.request.HTTPSHandler(context=context))
    return urllib.request.build_opener(*handlers)
