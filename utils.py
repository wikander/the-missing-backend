# json_utils.py
from __future__ import annotations

import re
from typing import Dict, List, Union, cast

INDEXED_KEY = re.compile(r'^(?P<key>[a-zA-Z0-9_]+)(\[(?P<index>\d*)\])?$')

# ---- JSON-typer ----
JSONValue = Union[str, int, float, bool, None, "JSONDict", "JSONList"]
JSONDict = Dict[str, JSONValue]
JSONList = List[JSONValue]


def set_by_path(
    data: JSONDict,
    path: str,
    value: JSONValue,
    sep: str = ".",
) -> None:
    parts = path.split(sep)
    cur: JSONDict = data  # alltid en dict

    for part in parts[:-1]:
        match = INDEXED_KEY.match(part)
        if not match:
            raise ValueError(f"Invalid path segment: {part}")

        key = match.group("key")
        idx = match.group("index")

        if idx is None:
            # ----- dict-access -----
            existing = cur.get(key)
            if not isinstance(existing, dict):
                cur[key] = {}
            cur = cast(JSONDict, cur[key])

        else:
            # ----- list-access -----
            existing = cur.get(key)
            if not isinstance(existing, list):
                cur[key] = []
            lst = cast(JSONList, cur[key])

            if idx == "":
                # append ny dict
                elem: JSONDict = {}
                lst.append(elem)
                cur = elem
            else:
                i = int(idx)
                while len(lst) <= i:
                    lst.append({})
                cur = cast(JSONDict, lst[i])

    # ----- Sätt slutvärdet -----
    final = parts[-1]
    match = INDEXED_KEY.match(final)
    if not match:
        raise ValueError(f"Invalid path segment: {final}")

    key = match.group("key")
    idx = match.group("index")

    if idx is None:
        cur[key] = value
    else:
        existing = cur.get(key)
        if not isinstance(existing, list):
            cur[key] = []
        lst = cast(JSONList, cur[key])

        if idx == "":
            lst.append(value)
        else:
            i = int(idx)
            while len(lst) <= i:
                lst.append(None)
            lst[i] = value
