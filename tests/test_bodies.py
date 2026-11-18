"""Bodies a response must not have: 1xx, 204, 205, 304, and HEAD."""

import json

import pytest
from mitmproxy.test import tutils

from mitten.responses import JSON_CONTENT_TYPE
from tests.helpers import make_flow, run_request, with_mocks


# ---- Forbidden bodies ----------------------------------------------------------


def short_circuit(sut, status, **request):
    with_mocks(sut, {"path": "/test", "method": "GET", "request": {"statusCode": status, **request}})
    flow = make_flow()
    run_request(sut, flow)
    assert flow.response is not None
    sut.response(flow)
    return flow.response


@pytest.mark.parametrize("status", [204, 205, 101])
def test_body_is_dropped_where_no_content_is_allowed(sut, status, caplog):
    response = short_circuit(sut, status, body={"a": 1})
    assert response.content == b""
    assert "Content-Type" not in response.headers
    assert response.headers.get("Content-Length") == ("0" if status == 205 else None)
    assert "mitten-mock-0.json" in caplog.text and "must not have a body" in caplog.text


def test_304_keeps_length_and_type_of_the_dropped_body(sut):
    response = short_circuit(sut, 304, body={"a": 1})
    assert response.content == b""
    assert response.headers["Content-Length"] == str(len(b'{"a": 1}'))
    assert response.headers["Content-Type"] == JSON_CONTENT_TYPE


def test_body_dropped_on_real_304_from_response_part(sut):
    with_mocks(sut, {"path": "/test", "method": "GET", "response": {"body": {"a": 1}}})
    flow = make_flow()
    run_request(sut, flow)
    flow.response = tutils.tresp(status_code=304, content=b"")
    sut.response(flow)
    assert flow.response.content == b""


def test_bodyless_status_without_body_is_untouched(sut):
    response = short_circuit(sut, 204)
    assert response.content == b""
    assert "Content-Length" in response.headers  # as mitmproxy made it


def test_body_kept_for_other_statuses(sut):
    response = short_circuit(sut, 200, body={"a": 1})
    assert response.json() == {"a": 1}


# ---- HEAD ----------------------------------------------------------------------


def head(sut, mock, server_response=None):
    with_mocks(sut, {"path": "/test", "method": "GET", **mock})
    flow = make_flow("HEAD", body=b"")
    run_request(sut, flow)
    if server_response is not None:
        assert flow.response is None  # forwarded
        flow.response = server_response
    assert flow.response is not None
    sut.response(flow)
    return flow.response


def test_head_short_circuit_is_the_get_answer_without_body(sut, caplog):
    body = {"name": "Luke"}
    response = head(sut, {"request": {"statusCode": 201, "headers": {"X-A": ["1"]}, "body": body}})
    assert response.status_code == 201
    assert response.content == b""
    assert response.headers["Content-Length"] == str(len(json.dumps(body)))
    assert response.headers["Content-Type"] == JSON_CONTENT_TYPE
    assert response.headers["X-A"] == "1"
    assert "must not have a body" not in caplog.text  # normal for HEAD, no warning


def test_head_fall_through_keeps_length_of_mocked_body(sut):
    server = tutils.tresp(content=b"")
    server.headers["Content-Length"] = "99"
    response = head(sut, {"response": {"statusCode": 202, "body": {"a": 1}}}, server)
    assert response.status_code == 202
    assert response.content == b""
    assert response.headers["Content-Length"] == str(len(b'{"a": 1}'))


def test_head_fall_through_without_body_keeps_server_headers(sut):
    server = tutils.tresp(content=b"")
    server.headers["Content-Length"] = "99"
    response = head(sut, {"response": {"headers": {"X-Mocked": ["true"]}}}, server)
    assert response.headers["Content-Length"] == "99"
    assert response.headers["X-Mocked"] == "true"


def test_head_on_204_follows_the_204_rules(sut):
    response = head(sut, {"request": {"statusCode": 204, "body": {"a": 1}}})
    assert response.content == b""
    assert "Content-Length" not in response.headers
