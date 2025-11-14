# json_utils.py
import re

INDEXED_KEY = re.compile(r'^(?P<key>[a-zA-Z0-9_]+)(\[(?P<index>\d*)\])?$')

def set_by_path(data, path, value, sep="."):
    parts = path.split(sep)
    cur = data

    for part in parts[:-1]:
        match = INDEXED_KEY.match(part)
        if not match:
            raise ValueError(f"Invalid path segment: {part}")

        key = match.group("key")
        idx = match.group("index")

        # ---- Ensure the key exists ----
        if key not in cur:
            # If next part is indexed -> create list
            if idx is not None:
                cur[key] = []
            else:
                cur[key] = {}

        # ---- Move into key ----
        if idx is None:
            # dict access
            if not isinstance(cur[key], dict):
                cur[key] = {}
            cur = cur[key]

        else:
            # list access
            lst = cur[key]
            if not isinstance(lst, list):
                lst = cur[key] = []

            if idx == "":
                # append new dict automatically
                lst.append({})
                cur = lst[-1]
            else:
                i = int(idx)
                # grow list if needed
                while len(lst) <= i:
                    lst.append({})
                cur = lst[i]

    # ---- Set final value ----
    final = parts[-1]
    match = INDEXED_KEY.match(final)
    key = match.group("key")
    idx = match.group("index")

    if idx is None:
        cur[key] = value
    else:
        if key not in cur or not isinstance(cur[key], list):
            cur[key] = []
        lst = cur[key]
        if idx == "":
            lst.append(value)
        else:
            i = int(idx)
            while len(lst) <= i:
                lst.append(None)
            lst[i] = value
