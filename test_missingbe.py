import asyncio
import io
import json
import random
from pathlib import Path

import pytest
from mitmproxy import exceptions
from mitmproxy import io as mitmproxy_io
from mitmproxy.test import taddons, tflow, tutils

from constants import HTTP_STATUS_CODES, HTTP_STATUS_PHRASES
from missingbe import (
    DEFAULT_SLEEP,
    DEFAULT_SLEEP_OPTION,
    JSON_CONTENT_TYPE,
    METADATA_KEY,
    SLEEP_PARAM,
    MissingBe,
    MockFileError,
    Sleep,
    SleepError,
    StatusSpec,
    load_mock_files,
    parse_mock,
    parse_sleep,
    parse_sleep_text,
)


@pytest.fixture
def sut():
    return MissingBe()


def make_flow(method="GET", path="/test", body=b"original"):
    req = tutils.treq(method=method.encode(), path=path.encode(), content=body)
    return tflow.tflow(req=req, resp=False)


def with_mocks(sut, *raw_mocks):
    sut.mocks = [parse_mock(m, f"mitten-mock-{i}.json") for i, m in enumerate(raw_mocks)]
    return sut


def run_request(sut, flow):
    asyncio.run(sut.request(flow))


# ---- Path matching -------------------------------------------------------------


def test_exact_match(sut):
    assert sut.comparePaths("/test", "/test") == {}

def test_no_match(sut):
    assert sut.comparePaths("/test", "/other") is None

def test_different_length(sut):
    assert sut.comparePaths("/api/people/1", "/test") is None

def test_single_param(sut):
    assert sut.comparePaths("/users/:id", "/users/42") == {"id": "42"}

def test_multiple_params(sut):
    assert sut.comparePaths("/users/:id/posts/:postId", "/users/42/posts/7") == {"id": "42", "postId": "7"}

def test_wildcard(sut):
    assert sut.comparePaths("/files/:*", "/files/a/b/c") == {}

def test_wildcard_with_param_before(sut):
    assert sut.comparePaths("/users/:id/:*", "/users/42/posts/extra") == {"id": "42"}

def test_no_match_with_wildcard(sut):
    assert sut.comparePaths("/users/:*/extra", "/other/thing") is None

def test_no_match_different_structure(sut):
    assert sut.comparePaths("/api/people/1", "/test") is None


# ---- Parsing -------------------------------------------------------------------


def test_only_path_and_method_are_required():
    mock = parse_mock({"path": "/test", "method": "GET"}, "f.json")
    assert (mock.methods, mock.request, mock.response) == (("GET",), None, None)

@pytest.mark.parametrize("data", [{}, {"path": "", "method": "GET"}, {"path": 1, "method": "GET"}, [], "x"])
def test_invalid_path_is_rejected(data):
    with pytest.raises(MockFileError):
        parse_mock(data, "f.json")

def test_method_is_upper_cased():
    assert parse_mock({"path": "/t", "method": "post"}, "f.json").methods == ("POST",)

def test_method_can_be_an_array():
    mock = parse_mock({"path": "/t", "method": ["get", "POST"]}, "f.json")
    assert mock.methods == ("GET", "POST")

@pytest.mark.parametrize("method", [None, "", " ", 1, [], ["GET", 1], ["GET", ""], {"GET": 1}])
def test_method_is_required(method):
    data = {"path": "/t"} if method is None else {"path": "/t", "method": method}
    with pytest.raises(MockFileError, match="method is required"):
        parse_mock(data, "f.json")

@pytest.mark.parametrize("method", ["HEAD", "head", ["GET", "HEAD"]])
def test_head_is_rejected(method):
    with pytest.raises(MockFileError, match="HEAD requests use the GET mocks"):
        parse_mock({"path": "/t", "method": method}, "f.json")

@pytest.mark.parametrize(
    "status",
    ["200", "4", 0, -4, 99, 1000, True, 2.5, 1, 10, 6, 48, [], [4, "5"], [[4]], {"min": 4}],
)
def test_invalid_status_is_rejected(status):
    with pytest.raises(MockFileError, match="statusCode"):
        parse_mock({"path": "/t", "method": "GET", "request": {"statusCode": status}}, "f.json")


def status_choices(raw):
    part = parse_mock({"path": "/t", "method": "GET", "request": {"statusCode": raw}}, "f.json").request
    assert part is not None and part.statusCode is not None
    return part.statusCode.choices


def test_exact_status_codes_need_not_be_registered():
    assert status_choices(404) == ((404,),)
    assert status_choices(299) == ((299,),)
    assert status_choices(101) == ((101,),)  # exact 1xx is allowed, just never random


def test_status_prefixes_pick_from_registered_codes():
    assert status_choices(4) == (tuple(c for c in HTTP_STATUS_CODES if 400 <= c < 500),)
    assert status_choices(40) == ((400, 401, 402, 403, 404, 405, 406, 407, 408, 409),)
    assert status_choices(51) == ((510, 511),)


def test_status_array_keeps_each_element_as_a_choice():
    assert status_choices([404, 50, 404]) == (
        (404,),
        (500, 501, 502, 503, 504, 505, 506, 507, 508),
        (404,),
    )


def test_status_array_picks_an_element_first():
    spec = StatusSpec(((404,), tuple(range(200, 210))))
    rng = random.Random(1)
    picks = [spec.pick(rng) for _ in range(4000)]
    assert 0.45 < picks.count(404) / len(picks) < 0.55
    assert set(picks) == {404, *range(200, 210)}

def test_disabled_headers_and_values_are_skipped():
    mock = parse_mock(
        {
            "path": "/t",
            "method": "GET",
            "request": {
                "headers": {
                    "_x_Authorization": ["Bearer xyz"],
                    "X-Feature": ["on", "_x_off"],
                    "X-Gone": ["_x_a"],
                }
            },
        },
        "f.json",
    )
    assert mock.request is not None
    assert [(h.key, h.values) for h in mock.request.headers] == [("X-Feature", ["on"])]

def test_single_string_header_value_is_accepted():
    mock = parse_mock({"path": "/t", "method": "GET", "response": {"headers": {"Accept": "text/plain"}}}, "f.json")
    assert mock.response is not None
    assert mock.response.headers[0].values == ["text/plain"]

def test_non_string_header_values_are_rejected():
    with pytest.raises(MockFileError, match="headers.X"):
        parse_mock({"path": "/t", "method": "GET", "request": {"headers": {"X": [1]}}}, "f.json")


# ---- Loading files -------------------------------------------------------------


def test_only_mitten_mock_files_are_loaded(tmp_path):
    (tmp_path / "mitten-mock-a.json").write_text('{"path": "/a", "method": "GET"}')
    (tmp_path / "response-old.json").write_text('{"path": "/old", "method": "GET"}')
    (tmp_path / "mitten-mock-notes.txt").write_text("not a mock")
    assert [m.source for m in load_mock_files(str(tmp_path))] == ["mitten-mock-a.json"]

def test_load_error_names_the_file(tmp_path):
    (tmp_path / "mitten-mock-bad.json").write_text("{not json")
    with pytest.raises(MockFileError, match="mitten-mock-bad.json"):
        load_mock_files(str(tmp_path))

def test_failed_load_keeps_previous_mocks(sut, tmp_path):
    (tmp_path / "mitten-mock-a.json").write_text('{"path": "/a", "method": "GET"}')
    sut.loadMockFiles(str(tmp_path))
    (tmp_path / "mitten-mock-b.json").write_text('{"method": "GET"}')
    with pytest.raises(MockFileError):
        sut.loadMockFiles(str(tmp_path))
    assert [m.source for m in sut.mocks] == ["mitten-mock-a.json"]


# ---- Matching ------------------------------------------------------------------


def test_method_must_match_case_insensitively(sut):
    with_mocks(sut, {"path": "/test", "method": "post"})
    assert sut.findMock(make_flow("POST")) is not None
    assert sut.findMock(make_flow("GET")) is None

def test_method_array_matches_each_method(sut):
    with_mocks(sut, {"path": "/test", "method": ["GET", "DELETE"]})
    assert sut.findMock(make_flow("DELETE")) is not None
    assert sut.findMock(make_flow("GET")) is not None
    assert sut.findMock(make_flow("POST")) is None

def test_head_uses_get_mocks(sut):
    with_mocks(sut, {"path": "/test", "method": ["GET", "POST"]}, {"path": "/other", "method": "POST"})
    assert sut.findMock(make_flow("HEAD", body=b"")) is not None
    assert sut.findMock(make_flow("HEAD", path="/other", body=b"")) is None

def test_query_string_is_ignored_when_matching(sut):
    with_mocks(sut, {"path": "/test", "method": "GET"})
    assert sut.findMock(make_flow(path="/test?a=1")) is not None


# ---- Request hook ----------------------------------------------------------------


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


# ---- Forbidden bodies ----------------------------------------------------------------


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


# ---- HEAD ----------------------------------------------------------------------------


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


# ---- Sleep -------------------------------------------------------------------------


@pytest.fixture
def slept(monkeypatch):
    """Record the delays the request hook waits for, without waiting."""
    delays = []

    async def fake_sleep(seconds):
        delays.append(round(seconds * 1000))

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    return delays


@pytest.mark.parametrize(
    "raw, expected",
    [(0, Sleep(0, 0)), (500, Sleep(500, 500)), ([200, 800], Sleep(200, 800)), ([5, 5], Sleep(5, 5))],
)
def test_valid_sleep_values(raw, expected):
    assert parse_sleep(raw) == expected


@pytest.mark.parametrize(
    "raw", [-1, 1.5, True, None, "500", [800, 200], [1], [1, 2, 3], [1, "2"], [-1, 5]]
)
def test_invalid_sleep_values_are_rejected(raw):
    with pytest.raises(SleepError):
        parse_sleep(raw)


@pytest.mark.parametrize("text", ["500", "[200,800]", "[200, 800]"])
def test_sleep_text_is_read_as_json(text):
    parse_sleep_text(text)


@pytest.mark.parametrize("text", ["", "abc", "200-800", "[200,800"])
def test_invalid_sleep_text_is_rejected(text):
    with pytest.raises(SleepError):
        parse_sleep_text(text)


def test_random_sleep_stays_in_range():
    rng = random.Random(1)
    picks = {Sleep(200, 210).pick(rng) for _ in range(200)}
    assert picks == set(range(200, 211))


def test_sleep_param_is_used_and_removed(sut, slept):
    sut.default_sleep = Sleep(9, 9)
    flow = make_flow(path=f"/test?a=1&{SLEEP_PARAM}=25&sleep=3")
    run_request(sut, flow)
    assert slept == [25]
    # The old unprefixed name is the backend's own param now, so it's forwarded.
    assert flow.request.path == "/test?a=1&sleep=3"


def test_default_sleep_without_param(sut, slept):
    sut.default_sleep = Sleep(40, 40)
    flow = make_flow(path="/test?flag")
    run_request(sut, flow)
    assert slept == [40]
    assert flow.request.path == "/test?flag"  # query not re-encoded


def test_sleep_param_zero_turns_default_off(sut, slept):
    sut.default_sleep = Sleep(40, 40)
    run_request(sut, make_flow(path=f"/test?{SLEEP_PARAM}=0"))
    assert slept == []


def test_invalid_sleep_param_falls_back_to_default(sut, slept):
    sut.default_sleep = Sleep(40, 40)
    flow = make_flow(path=f"/test?{SLEEP_PARAM}=abc")
    run_request(sut, flow)
    assert slept == [40]
    assert SLEEP_PARAM not in flow.request.query


def test_sleep_applies_to_short_circuits_too(sut, slept):
    with_mocks(sut, {"path": "/test", "method": "GET", "request": {"statusCode": 200}})
    flow = make_flow(path=f"/test?{SLEEP_PARAM}=[30,30]")
    run_request(sut, flow)
    assert slept == [30]
    assert flow.response is not None
    assert flow.metadata[METADATA_KEY] == {"sleep_ms": 30, "mock": "mitten-mock-0.json"}
    mitmproxy_io.FlowWriter(io.BytesIO()).add(flow)  # raises if not serializable


def test_default_sleep_option(sut):
    with taddons.context(sut) as tctx:
        assert getattr(tctx.options, DEFAULT_SLEEP_OPTION) == DEFAULT_SLEEP == "[50,700]"
        tctx.configure(sut, **{DEFAULT_SLEEP_OPTION: "0"})
        assert sut.default_sleep == Sleep(0, 0)
        tctx.configure(sut, **{DEFAULT_SLEEP_OPTION: "[10,20]"})
        assert sut.default_sleep == Sleep(10, 20)
        with pytest.raises(exceptions.OptionsError):
            tctx.configure(sut, **{DEFAULT_SLEEP_OPTION: "[20,10]"})
        assert sut.default_sleep == Sleep(10, 20)

def test_flow_metadata_stays_serializable(sut):
    with_mocks(sut, {"path": "/test", "method": "GET", "request": {"statusCode": 200}})
    flow = make_flow()
    run_request(sut, flow)
    assert flow.metadata[METADATA_KEY] == {"mock": "mitten-mock-0.json"}
    mitmproxy_io.FlowWriter(io.BytesIO()).add(flow)  # raises if not serializable


# ---- Response hook ---------------------------------------------------------------


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


def test_example_files_are_valid():
    mocks = load_mock_files(str(Path(__file__).parent / "example-responses"))
    assert len(mocks) >= 4
