"""Client tests run against httpx2.MockTransport: no network, no token, and
the same code path as a real request."""

import httpx2
import pytest

from canvas_mcp.client import CanvasClient, CanvasError, error_message


@pytest.fixture(autouse=True)
def _token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CANVAS_TOKEN", "fake-token-for-tests")


def client_returning(
    status_code: int = 200,
    json: object = None,
    capture: list[httpx2.Request] | None = None,
) -> CanvasClient:
    def handler(request: httpx2.Request) -> httpx2.Response:
        if capture is not None:
            capture.append(request)
        return httpx2.Response(status_code, json=json if json is not None else {})

    return CanvasClient(transport=httpx2.MockTransport(handler))


def test_get_returns_parsed_json() -> None:
    with client_returning(json=[{"id": 1, "name": "Datastructuren"}]) as client:
        assert client.get("/courses") == [{"id": 1, "name": "Datastructuren"}]


def test_request_carries_the_token_and_hits_the_api_prefix() -> None:
    seen: list[httpx2.Request] = []
    with client_returning(capture=seen) as client:
        client.get("/courses", params={"enrollment_state": "active"})

    request = seen[0]
    assert request.headers["Authorization"] == "Bearer fake-token-for-tests"
    assert request.url.path == "/api/v1/courses"
    assert request.url.params["enrollment_state"] == "active"


def test_missing_token_fails_before_any_request() -> None:
    import os

    os.environ.pop("CANVAS_TOKEN")
    with pytest.raises(CanvasError, match="CANVAS_TOKEN is not set"):
        CanvasClient()


def test_401_explains_that_tokens_expire() -> None:
    with client_returning(401) as client:
        with pytest.raises(CanvasError) as excinfo:
            client.get("/courses")

    message = str(excinfo.value)
    assert "90 days" in message
    assert "CANVAS_TOKEN" in message


def test_403_on_the_file_index_points_at_list_materials() -> None:
    message = error_message(403, "/courses/60059/files")
    assert "list_materials" in message


def test_403_elsewhere_does_not_give_file_advice() -> None:
    message = error_message(403, "/courses/60059/grades")
    assert "list_materials" not in message
    assert "/courses/60059/grades" in message


def test_404_does_not_claim_the_course_is_absent() -> None:
    message = error_message(404, "/courses/60059")
    assert "enrollment" in message


def test_unmapped_status_still_names_the_code_and_path() -> None:
    assert error_message(429, "/courses") == "Canvas returned 429 for /courses."


def test_verify_token_calls_users_self() -> None:
    seen: list[httpx2.Request] = []
    with client_returning(json={"id": 1}, capture=seen) as client:
        assert client.verify_token() == {"id": 1}
    assert seen[0].url.path == "/api/v1/users/self"


def test_unreachable_host_names_the_base_url() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("nope", request=request)

    with CanvasClient(transport=httpx2.MockTransport(handler)) as client:
        with pytest.raises(CanvasError, match="Could not reach Canvas"):
            client.get("/courses")
