import random
from pathlib import Path

import pytest

from mitten.http_status import HTTP_STATUS_CODES
from mitten.mock_file import MockFileError, StatusSpec, load_mock_files, parse_mock


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
    with pytest.raises(MockFileError, match="headers.X must be a string or a list of strings"):
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

def test_non_utf8_file_is_a_mock_file_error(tmp_path):
    (tmp_path / "mitten-mock-latin1.json").write_bytes('{"path": "/s\xf6ka", "method": "GET"}'.encode("latin-1"))
    with pytest.raises(MockFileError, match="mitten-mock-latin1.json: not UTF-8"):
        load_mock_files(str(tmp_path))

def test_missing_directory_is_a_mock_file_error(tmp_path):
    with pytest.raises(MockFileError, match="gone"):
        load_mock_files(str(tmp_path / "gone"))

def test_unreadable_file_is_a_mock_file_error(tmp_path):
    (tmp_path / "mitten-mock-dir.json").mkdir()  # not a file: skipped
    target = tmp_path / "mitten-mock-locked.json"
    target.write_text('{"path": "/a", "method": "GET"}')
    target.chmod(0)
    try:
        with pytest.raises(MockFileError, match="mitten-mock-locked.json"):
            load_mock_files(str(tmp_path))
    finally:
        target.chmod(0o644)

def test_failed_load_keeps_previous_mocks(sut, tmp_path):
    (tmp_path / "mitten-mock-a.json").write_text('{"path": "/a", "method": "GET"}')
    sut.load_mock_files(str(tmp_path))
    (tmp_path / "mitten-mock-b.json").write_text('{"method": "GET"}')
    with pytest.raises(MockFileError):
        sut.load_mock_files(str(tmp_path))
    assert [m.source for m in sut.mocks] == ["mitten-mock-a.json"]


def test_example_files_are_valid():
    mocks = load_mock_files(str(Path(__file__).parent.parent / "example-responses"))
    assert len(mocks) >= 4
