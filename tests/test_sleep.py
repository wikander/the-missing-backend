import io
import random

import pytest
from mitmproxy import exceptions
from mitmproxy import io as mitmproxy_io
from mitmproxy.test import taddons

from missingbe import DEFAULT_SLEEP, DEFAULT_SLEEP_OPTION, METADATA_KEY, SLEEP_PARAM
from mitten.sleep import Sleep, SleepError, parse_sleep, parse_sleep_text
from tests.helpers import make_flow, run_request, with_mocks


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
    assert flow.metadata[METADATA_KEY] == {"sleep_ms": 30, "mock": "mitten-mock-0.json", "short_circuit": True}
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
