"""Helpers shared by the tests."""

import asyncio

from mitmproxy.test import tflow, tutils

from mitten.mock_file import parse_mock


def make_flow(method="GET", path="/test", body=b"original"):
    req = tutils.treq(method=method.encode(), path=path.encode(), content=body)
    return tflow.tflow(req=req, resp=False)


def with_mocks(sut, *raw_mocks):
    sut.mocks = [parse_mock(m, f"mitten-mock-{i}.json") for i, m in enumerate(raw_mocks)]
    return sut


def run_request(sut, flow):
    asyncio.run(sut.request(flow))
