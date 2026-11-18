import io
import random

import pytest
from mitmproxy import io as mitmproxy_io
from mitmproxy.test import tutils

from missingbe import METADATA_KEY
from mitten.http_status import HTTP_STATUS_PHRASES
from mitten.responses import JSON_CONTENT_TYPE
from tests.helpers import make_flow, run_request, with_mocks


# ---- Request hook --------------------------------------------------------------


def test_status_code_in_request_short_circuits(sut):
    with_mocks(
        sut,
        {
            "path": "/test",
            "method": "GET",
            "request": {
                "statusCode": 404,
                "headers": {"Set-Cookie": ["a=1", "b=2"]},
                "body": {"error": "nope"},
            },
        },
    )
    flow = make_flow()
    run_request(sut, flow)

    assert flow.response is not None
    assert flow.response.status_code == 404
    assert flow.response.reason == "Not Found"
    assert flow.response.json() == {"error": "nope"}
    assert flow.response.headers["Content-Type"] == JSON_CONTENT_TYPE
    assert flow.response.headers.get_all("Set-Cookie") == ["a=1", "b=2"]

def test_short_circuit_without_body_is_empty(sut):
    with_mocks(sut, {"path": "/test", "method": "DELETE", "request": {"statusCode": 204}})
    flow = make_flow("DELETE")
    run_request(sut, flow)

    assert flow.response is not None
    assert flow.response.status_code == 204
    assert flow.response.content == b""
    assert "Content-Type" not in flow.response.headers

@pytest.mark.parametrize("body", [[], {}, 0, False, ""])
def test_falsy_json_bodies_are_still_sent(sut, body):
    with_mocks(sut, {"path": "/test", "method": "GET", "request": {"statusCode": 200, "body": body}})
    flow = make_flow()
    run_request(sut, flow)
    assert flow.response is not None
    assert flow.response.json() == body

def test_mock_content_type_is_kept(sut):
    with_mocks(
        sut,
        {
            "path": "/test",
            "method": "GET",
            "request": {
                "statusCode": 200,
                "headers": {"Content-Type": ["application/problem+json"]},
                "body": {"title": "x"},
            },
        },
    )
    flow = make_flow()
    run_request(sut, flow)
    assert flow.response is not None
    assert flow.response.headers.get_all("Content-Type") == ["application/problem+json"]

def test_request_without_status_code_is_altered_and_forwarded(sut):
    with_mocks(
        sut,
        {
            "path": "/test",
            "method": "POST",
            "request": {
                "headers": {"X-Mocked-By": ["missingbe"], "Accept": ["a", "b"]},
                "body": {"altered": True},
            },
        },
    )
    flow = make_flow("POST")
    flow.request.headers["Accept"] = "original"
    run_request(sut, flow)

    assert flow.response is None
    assert flow.request.headers["X-Mocked-By"] == "missingbe"
    assert flow.request.headers.get_all("Accept") == ["a", "b"]
    assert flow.request.json() == {"altered": True}
    assert flow.request.headers["Content-Type"] == JSON_CONTENT_TYPE

def test_unmatched_request_is_untouched(sut):
    with_mocks(sut, {"path": "/other", "method": "GET", "request": {"statusCode": 200}})
    flow = make_flow()
    run_request(sut, flow)
    assert flow.response is None
    assert flow.request.content == b"original"
    assert METADATA_KEY not in flow.metadata

def test_short_circuit_status_is_picked_per_request(sut):
    with_mocks(sut, {"path": "/test", "method": "GET", "request": {"statusCode": 5}})
    sut.rng = random.Random(3)
    statuses = set()
    for _ in range(40):
        flow = make_flow()
        run_request(sut, flow)
        assert flow.response is not None
        assert flow.response.reason == HTTP_STATUS_PHRASES[flow.response.status_code]
        statuses.add(flow.response.status_code)
    assert len(statuses) > 1
    assert all(500 <= s < 600 for s in statuses)


@pytest.mark.parametrize("status, reason", [(408, "Request Timeout"), (299, "")])
def test_reason_phrases_come_from_constants(sut, status, reason):
    with_mocks(sut, {"path": "/test", "method": "GET", "request": {"statusCode": status}})
    flow = make_flow()
    run_request(sut, flow)
    assert flow.response is not None
    assert (flow.response.status_code, flow.response.reason) == (status, reason)


def test_flow_metadata_stays_serializable(sut):
    with_mocks(sut, {"path": "/test", "method": "GET", "request": {"statusCode": 200}})
    flow = make_flow()
    run_request(sut, flow)
    assert flow.metadata[METADATA_KEY] == {"mock": "mitten-mock-0.json", "short_circuit": True}
    mitmproxy_io.FlowWriter(io.BytesIO()).add(flow)  # raises if not serializable


# ---- Response hook -------------------------------------------------------------


def test_response_part_overrides_real_response(sut):
    with_mocks(
        sut,
        {"path": "/test", "method": "GET", "response": {"statusCode": 503, "headers": {"X-Mocked": ["true"]}}},
    )
    flow = make_flow()
    run_request(sut, flow)
    flow.response = tutils.tresp(content=b"from server")
    sut.response(flow)

    assert flow.response.status_code == 503
    assert flow.response.reason == "Service Unavailable"
    assert flow.response.headers["X-Mocked"] == "true"
    assert flow.response.content == b"from server"  # body not set: kept

def test_response_part_status_prefix_on_real_response(sut):
    with_mocks(sut, {"path": "/test", "method": "GET", "response": {"statusCode": [41, 50]}})
    flow = make_flow()
    run_request(sut, flow)
    flow.response = tutils.tresp(content=b"from server")
    sut.response(flow)

    assert flow.response.status_code in (*range(410, 420), *range(500, 510))
    assert flow.response.reason == HTTP_STATUS_PHRASES[flow.response.status_code]
    assert flow.response.content == b"from server"

def test_response_part_replaces_body(sut):
    with_mocks(sut, {"path": "/test", "method": "GET", "response": {"body": {"patched": 1}}})
    flow = make_flow()
    run_request(sut, flow)
    flow.response = tutils.tresp()
    sut.response(flow)

    assert flow.response.json() == {"patched": 1}
    assert flow.response.headers["Content-Type"] == JSON_CONTENT_TYPE

def test_response_part_applies_after_short_circuit(sut):
    with_mocks(
        sut,
        {
            "path": "/test",
            "method": "GET",
            "request": {"statusCode": 200, "body": {"a": 1}},
            "response": {"headers": {"X-Mocked": ["true"]}},
        },
    )
    flow = make_flow()
    run_request(sut, flow)
    assert flow.response is not None
    sut.response(flow)

    assert flow.response.json() == {"a": 1}
    assert flow.response.headers["X-Mocked"] == "true"

def test_response_of_unmatched_flow_is_untouched(sut):
    with_mocks(sut, {"path": "/other", "method": "GET", "response": {"statusCode": 500}})
    flow = make_flow()
    run_request(sut, flow)
    flow.response = tutils.tresp()
    sut.response(flow)
    assert flow.response.status_code == 200
