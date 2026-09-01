"""HTTP layer for the Canvas API: authentication, one request path, and the
translation of status codes into errors a model can act on."""

import os
from collections.abc import Iterator
from typing import Any

import httpx2

DEFAULT_BASE_URL = "https://canvas.uva.nl"
DEFAULT_TIMEOUT = 10.0
API_PREFIX = "/api/v1"
# Canvas defaults to 10 items per page, which silently truncates every list.
DEFAULT_PER_PAGE = 100
# A cap on how far paginate() will follow rel="next" before giving up.
MAX_PAGES = 50


class CanvasError(RuntimeError):
    """Raised for anything the caller cannot fix by trying again.

    The message is the interface. It is read by a model deciding what to do
    next, not by a human reading a log line, so it says what went wrong *and*
    what to do about it. See SCOPE.md section 9.
    """


def error_message(status_code: int, path: str) -> str:
    """Map a Canvas status code to an instruction.

    Kept separate from the client so it can be tested without a transport.
    """
    if status_code == 401:
        return (
            "Canvas token rejected. Personal access tokens expire after at "
            "most 90 days — generate a new one at canvas.uva.nl under "
            "Account → Settings and put it in CANVAS_TOKEN."
        )
    if status_code == 403:
        hint = ""
        if path.rstrip("/").endswith("/files"):
            hint = (
                " The course file index requires teacher permissions; use "
                "list_materials instead, which reads the module tree."
            )
        return f"Not authorised for {path}.{hint}"
    if status_code == 404:
        return (
            f"{path} was not found, or is not visible with this enrollment. "
            "Canvas hides what you are not enrolled in rather than refusing "
            "it, so these two cases look the same from here."
        )
    return f"Canvas returned {status_code} for {path}."


def _path_of(url: str) -> str:
    """A URL with its query removed, safe to put in a message."""
    return str(httpx2.URL(url).copy_with(query=None, fragment=None))


def _too_large(size: int, limit: int) -> str:
    return (
        f"That file is {size // 1_000_000} MB, over the {limit // 1_000_000} MB "
        "this server will read. Open it in Canvas instead."
    )


class CanvasClient:
    """A read-only Canvas API client.

    The token is read from the environment and never accepted as an argument,
    so no tool signature can be talked into carrying one.
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        transport: Any = None,
    ) -> None:
        token = os.environ.get("CANVAS_TOKEN", "").strip()
        if not token:
            raise CanvasError(
                "CANVAS_TOKEN is not set. Create a personal access token at "
                "canvas.uva.nl under Account → Settings and put it in the "
                "environment, or run with --demo to use stored fixtures."
            )
        configured = base_url or os.environ.get("CANVAS_BASE_URL") or DEFAULT_BASE_URL
        root = configured.rstrip("/")
        self.base_url = root
        self._client = httpx2.Client(
            base_url=root + API_PREFIX,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            },
            timeout=timeout,
            transport=transport,
        )

    def _request(
        self,
        url: str,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> httpx2.Response:
        """One GET with the error mapping applied.

        `url` is what gets fetched — a path on the first request, an absolute
        rel="next" URL afterwards. `path` is only used for error messages, so
        that page four of /courses still reports /courses.
        """
        try:
            response = self._client.get(url, params=params)
        except httpx2.RequestError as exc:
            raise CanvasError(
                f"Could not reach Canvas at {self.base_url}: {exc}"
            ) from exc
        if response.status_code >= 400:
            raise CanvasError(error_message(response.status_code, path))
        return response

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """Perform one GET and return parsed JSON, or raise CanvasError."""
        return self._request(path, path, params).json()

    def paginate(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        per_page: int = DEFAULT_PER_PAGE,
    ) -> Iterator[Any]:
        """Yield every item of a list endpoint, across every page.

        Items rather than pages: every caller wants to iterate results, and
        yielding pages would push a second loop into all of them.
        """
        query: dict[str, Any] | None = {"per_page": per_page, **(params or {})}
        url = path
        for _ in range(MAX_PAGES):
            response = self._request(url, path, query)
            payload = response.json()
            if not isinstance(payload, list):
                raise CanvasError(
                    f"{path} returned a single object, not a list, so it "
                    "cannot be paginated. Use get() for this endpoint."
                )
            yield from payload

            next_link = response.links.get("next")
            if next_link is None:
                return
            # The rel="next" URL already carries the query string; sending
            # params again would duplicate every parameter.
            url = next_link["url"]
            query = None

        raise CanvasError(
            f"{path} still had more pages after {MAX_PAGES}. Refusing to keep "
            "following them — narrow the request instead."
        )

    def get_bytes(self, url: str, max_bytes: int) -> bytes:
        """Fetch a file, refusing one larger than `max_bytes`.

        The size is checked from the response header before the body is read,
        and again against what actually arrived: a server that understates
        Content-Length should not be able to spend a caller's memory.
        """
        try:
            with self._client.stream(
                "GET",
                url,
                # Canvas answers a file URL with a redirect to a signed
                # location. Without this the body is empty and the failure
                # arrives later, as "not a readable PDF".
                follow_redirects=True,
                # The client asks for JSON everywhere else; a PDF is not that.
                headers={"Accept": "*/*"},
            ) as response:
                if response.status_code >= 400:
                    # The path, never the query: a Canvas file URL carries a
                    # verifier, which is an unauthenticated download link and
                    # is exactly what SCOPE.md section 5 keeps out of output.
                    raise CanvasError(
                        error_message(response.status_code, _path_of(url))
                    )
                declared = response.headers.get("content-length")
                if declared and int(declared) > max_bytes:
                    raise CanvasError(_too_large(int(declared), max_bytes))

                body = bytearray()
                for chunk in response.iter_bytes():
                    body += chunk
                    if len(body) > max_bytes:
                        raise CanvasError(_too_large(len(body), max_bytes))
                return bytes(body)
        except httpx2.RequestError as exc:
            raise CanvasError(
                f"Could not reach Canvas at {self.base_url}: {exc}"
            ) from exc

    def verify_token(self) -> dict[str, Any]:
        """Check the token once at startup and fail fast if it is dead.

        A token that expired between two sessions otherwise surfaces as a
        confusing 401 in the middle of an unrelated tool call.
        """
        return self.get("/users/self")

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "CanvasClient":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
