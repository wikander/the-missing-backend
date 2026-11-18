import asyncio
import io
import random
from pathlib import Path

import pytest
from mitmproxy import exceptions
from mitmproxy import io as mitmproxy_io
from mitmproxy.test import taddons, tflow, tutils

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


def test_only_path_is_required():
    mock = parse_mock({"path": "/test"}, "f.json")
    assert (mock.method, mock.request, mock.response) == (None, None, None)

@pytest.mark.parametrize("data", [{}, {"path": ""}, {"path": 1}, [], "x"])
def test_invalid_path_is_rejected(data):
    with pytest.raises(MockFileError):
        parse_mock(data, "f.json")

def test_method_is_upper_cased():
    assert parse_mock({"path": "/t", "method": "post"}, "f.json").method == "POST"

@pytest.mark.parametrize("status", ["200", 99, 1000, True, 2.5])
def test_invalid_status_is_rejected(status):
    with pytest.raises(MockFileError, match="statusCode"):
        parse_mock({"path": "/t", "request": {"statusCode": status}}, "f.json")

def test_disabled_headers_and_values_are_skipped():
    mock = parse_mock(
        {
            "path": "/t",
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
    mock = parse_mock({"path": "/t", "response": {"headers": {"Accept": "text/plain"}}}, "f.json")
    assert mock.response is not None
    assert mock.response.headers[0].values == ["text/plain"]

def test_non_string_header_values_are_rejected():
    with pytest.raises(MockFileError, match="headers.X"):
        parse_mock({"path": "/t", "request": {"headers": {"X": [1]}}}, "f.json")


# ---- Loading files -------------------------------------------------------------


def test_only_mitten_mock_files_are_loaded(tmp_path):
    (tmp_path / "mitten-mock-a.json").write_text('{"path": "/a"}')
    (tmp_path / "response-old.json").write_text('{"path": "/old"}')
    (tmp_path / "mitten-mock-notes.txt").write_text("not a mock")
    assert [m.source for m in load_mock_files(str(tmp_path))] == ["mitten-mock-a.json"]

def test_load_error_names_the_file(tmp_path):
    (tmp_path / "mitten-mock-bad.json").write_text("{not json")
    with pytest.raises(MockFileError, match="mitten-mock-bad.json"):
        load_mock_files(str(tmp_path))

def test_failed_load_keeps_previous_mocks(sut, tmp_path):
    (tmp_path / "mitten-mock-a.json").write_text('{"path": "/a"}')
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

def test_missing_method_matches_any(sut):
    with_mocks(sut, {"path": "/test"})
    assert sut.findMock(make_flow("DELETE")) is not None

def test_query_string_is_ignored_when_matching(sut):
    with_mocks(sut, {"path": "/test"})
    assert sut.findMock(make_flow(path="/test?a=1")) is not None


# ---- Request hook ----------------------------------------------------------------


def test_status_code_in_request_short_circuits(sut):
    with_mocks(
        sut,
        {
            "path": "/test",
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
    with_mocks(sut, {"path": "/test", "request": {"statusCode": 200, "body": body}})
    flow = make_flow()
    run_request(sut, flow)
    assert flow.response is not None
    assert flow.response.json() == body

def test_mock_content_type_is_kept(sut):
    with_mocks(
        sut,
        {
            "path": "/test",
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
    with_mocks(sut, {"path": "/other", "request": {"statusCode": 200}})
    flow = make_flow()
    run_request(sut, flow)
    assert flow.response is None
    assert flow.request.content == b"original"
    assert METADATA_KEY not in flow.metadata

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
    with_mocks(sut, {"path": "/test", "request": {"statusCode": 200}})
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
    with_mocks(sut, {"path": "/test", "request": {"statusCode": 200}})
    flow = make_flow()
    run_request(sut, flow)
    assert flow.metadata[METADATA_KEY] == {"mock": "mitten-mock-0.json"}
    mitmproxy_io.FlowWriter(io.BytesIO()).add(flow)  # raises if not serializable


# ---- Response hook ---------------------------------------------------------------


def test_response_part_overrides_real_response(sut):
    with_mocks(
        sut,
        {"path": "/test", "response": {"statusCode": 503, "headers": {"X-Mocked": ["true"]}}},
    )
    flow = make_flow()
    run_request(sut, flow)
    flow.response = tutils.tresp(content=b"from server")
    sut.response(flow)

    assert flow.response.status_code == 503
    assert flow.response.reason == "Service Unavailable"
    assert flow.response.headers["X-Mocked"] == "true"
    assert flow.response.content == b"from server"  # body not set: kept

def test_response_part_replaces_body(sut):
    with_mocks(sut, {"path": "/test", "response": {"body": {"patched": 1}}})
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
    with_mocks(sut, {"path": "/other", "response": {"statusCode": 500}})
    flow = make_flow()
    run_request(sut, flow)
    flow.response = tutils.tresp()
    sut.response(flow)
    assert flow.response.status_code == 200


def test_example_files_are_valid():
    mocks = load_mock_files(str(Path(__file__).parent / "example-responses"))
    assert len(mocks) >= 4
