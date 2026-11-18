# 6. Status code prefixes and sets

Date: 2026-11-18

## Status

Accepted. `constants.py` is now `mitten/http_status.py`
([ADR 0010](0010-mitten-package-layout.md)).

## Context

`statusCode` in a mock part was a single integer, 100–999. Testing how a
client handles errors meant writing one mock file per status code, and
relying on the random choice between files with the same `path` to vary
them.

Reason phrases came from mitmproxy's own table, which uses older wording
(`Request Time-out`) and includes two unregistered nginx codes (444, 499).
mitmproxy only fills in the reason when a response is created, not when
`status_code` is changed.

## Decision

- `constants.py` holds the IANA registered status codes with their RFC 9110
  reason phrases. 418 is included although it is only reserved.
- `statusCode` accepts:
  - an integer 100–999: that exact code, registered or not;
  - an integer with one or two digits: a prefix, picking among the
    registered codes that start with it (`4` → 4xx, `40` → 400–409);
  - an array of the above: an element is picked first, then a code within
    it, so `[2, 404]` gives 404 half the time and repeating an element
    weights it.
- 1xx codes are never picked at random, because they aren't final
  responses. Prefixes `1` and `10`, prefixes that match no code, empty
  arrays and nested arrays are load errors.
- Arrays are sets, never ranges. `sleep` uses `[min, max]` as a range, but
  status codes are discrete, and an array meaning a range in one field and a
  set in another would be ambiguous to read. Prefixes cover the common
  ranges; a string range such as `"401-403"` could be added later without
  breaking anything.
- The code is picked again for every request, in both the `request` and
  `response` parts.
- The reason phrase is always set from `constants.py`, also after
  `Response.make`, so it matches the picked code.
- A `body` is sent with whatever code is picked, including 204 and 304. The
  mock's author chose the body; leaving it out silently would be surprising.

## Consequences

- One mock file can return varying codes, for example `"statusCode": 5` on
  a fall-through `response` part for random server errors on real data.
- Prefix picks are uniform over registered codes, so `4` returns 418 or 421
  as often as 404. A set gives control over which codes and how often.
- Reason phrases change for codes where mitmproxy's wording differed, and
  444 and 499 now get an empty reason.
- `missingbe.py` imports `constants.py` from the same folder. mitmproxy puts
  the script's folder on `sys.path` while loading it. A hot reload of
  `missingbe.py` doesn't reload `constants.py`; that needs a restart.
