import io

import pytest
from mitmproxy import exceptions
from mitmproxy import io as mitmproxy_io
from mitmproxy.test import taddons, tutils

from missingbe import CORS_OPTION
from mitten.cors import CorsMode
from tests.helpers import make_flow, run_request, with_mocks

ORIGIN = "http://localhost:5173"
SHORT_CIRCUIT_PUT = {"path": "/test", "method": "PUT", "request": {"statusCode": 200, "body": {"a": 1}}}


def preflight(method="PUT", path="/test", headers="content-type, authorization"):
    flow = make_flow("OPTIONS", path=path, body=b"")
    flow.request.headers["Origin"] = ORIGIN
    flow.request.headers["Access-Control-Request-Method"] = method
    if headers:
        flow.request.headers["Access-Control-Request-Headers"] = headers
    return flow


def with_origin(flow):
    flow.request.headers["Origin"] = ORIGIN
    return flow


def finish(sut, flow, server_response=None):
    run_request(sut, flow)
    if flow.response is None:
        flow.response = server_response or tutils.tresp()
    sut.response(flow)
    return flow.response


def test_cors_option_defaults_to_mocks_and_validates(sut):
    with taddons.context(sut) as tctx:
        assert getattr(tctx.options, CORS_OPTION) == "mocks"
        tctx.configure(sut, **{CORS_OPTION: "all"})
        assert sut.cors == CorsMode.ALL
        with pytest.raises(exceptions.OptionsError):
            tctx.configure(sut, **{CORS_OPTION: "yes"})
        assert sut.cors == CorsMode.ALL


def test_preflight_for_short_circuit_is_answered(sut):
    with_mocks(sut, SHORT_CIRCUIT_PUT)
    flow = preflight()
    run_request(sut, flow)
    response = flow.response
    assert response is not None
    assert response.status_code == 204 and response.content == b""
    assert "Content-Length" not in response.headers
    assert response.headers["Access-Control-Allow-Origin"] == ORIGIN
    assert response.headers["Access-Control-Allow-Methods"] == "PUT"
    assert response.headers["Access-Control-Allow-Headers"] == "content-type, authorization"
    assert response.headers["Access-Control-Allow-Credentials"] == "true"
    assert "Origin" in response.headers["Vary"]
    sut.response(flow)  # CORS headers aren't added a second time
    assert response.headers.get_all("Access-Control-Allow-Origin") == [ORIGIN]
    mitmproxy_io.FlowWriter(io.BytesIO()).add(flow)  # metadata stays serializable


@pytest.mark.parametrize(
    "mocks, method",
    [
        ([SHORT_CIRCUIT_PUT], "DELETE"),  # no mock for the requested method
        ([{"path": "/test", "method": "PUT", "request": {"headers": {"X": ["1"]}}}], "PUT"),  # forwards
        ([{"path": "/test", "method": "PUT"}], "PUT"),  # no request part: forwards
        ([], "PUT"),
    ],
)
def test_preflight_goes_to_server_in_mocks_mode_unless_short_circuited(sut, mocks, method):
    with_mocks(sut, *mocks)
    flow = preflight(method)
    run_request(sut, flow)
    assert flow.response is None


def test_preflight_is_answered_for_everything_in_all_mode(sut):
    sut.cors = CorsMode.ALL
    flow = preflight("DELETE", path="/unmocked")
    run_request(sut, flow)
    assert flow.response is not None and flow.response.status_code == 204


def test_preflight_goes_to_server_when_off(sut):
    with_mocks(sut, SHORT_CIRCUIT_PUT)
    sut.cors = CorsMode.OFF
    flow = preflight()
    run_request(sut, flow)
    assert flow.response is None


def test_plain_options_still_uses_options_mocks(sut):
    with_mocks(sut, {"path": "/test", "method": "OPTIONS", "request": {"statusCode": 200, "body": "x"}})
    flow = with_origin(make_flow("OPTIONS", body=b""))  # no Access-Control-Request-Method
    run_request(sut, flow)
    assert flow.response is not None and flow.response.json() == "x"


def test_short_circuit_gets_cors_headers(sut):
    with_mocks(sut, {"path": "/test", "method": "GET", "request": {"statusCode": 201, "headers": {"Location": ["/x"]}, "body": {"a": 1}}})
    response = finish(sut, with_origin(make_flow()))
    assert response.headers["Access-Control-Allow-Origin"] == ORIGIN
    assert response.headers["Access-Control-Allow-Credentials"] == "true"
    exposed = [h.strip().lower() for h in response.headers["Access-Control-Expose-Headers"].split(",")]
    assert "location" in exposed and "content-type" in exposed
    assert not any(h.startswith("access-control-") for h in exposed)
    assert response.headers["Vary"] == "Origin"


def test_no_cors_headers_without_origin(sut):
    with_mocks(sut, {"path": "/test", "method": "GET", "request": {"statusCode": 200}})
    response = finish(sut, make_flow())
    assert "Access-Control-Allow-Origin" not in response.headers


def test_fall_through_keeps_server_cors_in_mocks_mode(sut):
    with_mocks(sut, {"path": "/test", "method": "GET", "response": {"headers": {"X-Mocked": ["true"]}}})
    server = tutils.tresp()
    server.headers["Access-Control-Allow-Origin"] = "https://app.example.com"
    response = finish(sut, with_origin(make_flow()), server)
    assert response.headers["Access-Control-Allow-Origin"] == "https://app.example.com"
    assert "Access-Control-Allow-Credentials" not in response.headers


def test_all_mode_overrides_server_cors_and_covers_unmatched(sut):
    sut.cors = CorsMode.ALL
    server = tutils.tresp()
    server.headers["Access-Control-Allow-Origin"] = "https://app.example.com"
    server.headers["Vary"] = "Accept-Encoding"
    response = finish(sut, with_origin(make_flow(path="/unmocked")), server)
    assert response.headers.get_all("Access-Control-Allow-Origin") == [ORIGIN]
    assert response.headers["Vary"] == "Accept-Encoding, Origin"


def test_off_mode_adds_nothing(sut):
    sut.cors = CorsMode.OFF
    with_mocks(sut, {"path": "/test", "method": "GET", "request": {"statusCode": 200}})
    response = finish(sut, with_origin(make_flow()))
    assert "Access-Control-Allow-Origin" not in response.headers
