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


def paging_client(
    pages: list[list[object]],
    capture: list[httpx2.Request] | None = None,
    never_ends: bool = False,
) -> CanvasClient:
    """A client whose transport serves `pages` and links them together."""

    def handler(request: httpx2.Request) -> httpx2.Response:
        if capture is not None:
            capture.append(request)
        index = int(request.url.params.get("page", 1)) - 1
        body = pages[min(index, len(pages) - 1)]
        headers = {}
        if never_ends or index < len(pages) - 1:
            nxt = request.url.copy_set_param("page", index + 2)
            headers["Link"] = f'<{nxt}>; rel="next"'
        return httpx2.Response(200, json=body, headers=headers)

    return CanvasClient(transport=httpx2.MockTransport(handler))


def test_paginate_flattens_every_page_in_order() -> None:
    with paging_client([[{"id": 1}, {"id": 2}], [{"id": 3}]]) as client:
        assert list(client.paginate("/courses")) == [{"id": 1}, {"id": 2}, {"id": 3}]


def test_paginate_stops_when_there_is_no_next_link() -> None:
    seen: list[httpx2.Request] = []
    with paging_client([[{"id": 1}]], capture=seen) as client:
        list(client.paginate("/courses"))
    assert len(seen) == 1


def test_paginate_asks_for_a_hundred_per_page_by_default() -> None:
    seen: list[httpx2.Request] = []
    with paging_client([[]], capture=seen) as client:
        list(client.paginate("/courses"))
    assert seen[0].url.params["per_page"] == "100"


def test_caller_params_and_per_page_are_not_repeated_on_later_pages() -> None:
    seen: list[httpx2.Request] = []
    with paging_client([[{"id": 1}], [{"id": 2}]], capture=seen) as client:
        list(client.paginate("/courses", params={"enrollment_state": "active"}))

    assert seen[0].url.params["enrollment_state"] == "active"
    # Page two follows the rel="next" URL, which already carries the query.
    assert seen[1].url.params.get_list("enrollment_state") == ["active"]
    assert seen[1].url.params.get_list("per_page") == ["100"]


def test_paginate_refuses_an_endpoint_that_returns_an_object() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json={"id": 1})

    with CanvasClient(transport=httpx2.MockTransport(handler)) as client:
        with pytest.raises(CanvasError, match="not a list"):
            list(client.paginate("/users/self"))


def test_paginate_maps_an_error_on_a_later_page() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        if "page" in request.url.params:
            return httpx2.Response(401)
        nxt = request.url.copy_set_param("page", 2)
        return httpx2.Response(
            200, json=[{"id": 1}], headers={"Link": f'<{nxt}>; rel="next"'}
        )

    with CanvasClient(transport=httpx2.MockTransport(handler)) as client:
        with pytest.raises(CanvasError, match="90 days"):
            list(client.paginate("/courses"))


def test_paginate_gives_up_rather_than_truncating_silently() -> None:
    with paging_client([[{"id": 1}]], never_ends=True) as client:
        with pytest.raises(CanvasError, match="Refusing to keep following"):
            list(client.paginate("/courses"))
