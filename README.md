# The Missing Backend

If you should agree on something, agree on this.

to run: `mitmproxy --mode reverse:http://localhost:3000 -s ./missingbe.py --set mock_dir=./example-responses --set connection_strategy=lazy -p 3001`

## Developing

Dependencies are managed with [uv](https://docs.astral.sh/uv/) (`brew install uv`). `pyproject.toml` lists them and `uv.lock` pins the exact versions; mitmproxy is the only runtime dependency, and Flask (for the test server) and pytest are in the `dev` group.

```
uv sync            # create .venv with exactly the locked versions
uv run pytest -q   # run the tests
```

Add a dependency with `uv add <package>` (or `uv add --dev <package>`), which updates both files. Don't edit `uv.lock` by hand.

The commands below use the mitmproxy on your `PATH`, for example from Homebrew. To use the project's own version instead, put `uv run` in front: `uv run mitmproxy ...`.

## Default behaviour

What the missing backend does when you don't configure anything.

### Options

| Option | Default | Meaning |
|---|---|---|
| `mock_dir` | `.` (the directory you start mitmproxy in) | Where `mitten-mock*.json` files are loaded from. |
| `mitten_default_sleep` | `[50,700]` | Delay in ms for requests without `?mitten-sleep=`. `0` turns it off. |
| `mitten_cors` | `mocks` | CORS for browser frontends on another origin: `off`, `mocks` or `all`. See [CORS](#cors). |

Set them with `--set name=value` on the command line, or `:set name=value` in mitmproxy.

**Always start mitmproxy with `--set connection_strategy=lazy`.** It's a mitmproxy option, not one of ours, and it is `eager` by default. In reverse mode, eager means mitmproxy connects to the backend as soon as a client connects, before the addon sees the request. If the backend is down or doesn't exist yet, every request fails with an empty reply, including requests a mock would answer. With `lazy`, mitmproxy only connects when a request is actually forwarded, so mocks work without a backend.

### Every request through the proxy

1. **Delayed.** Each request waits a random 50–700 ms before anything else happens, whether a mock matches or not. `?mitten-sleep=500` (exactly 500 ms) or `?mitten-sleep=[200,800]` (random in that range) sets the delay for that request instead, and `?mitten-sleep=0` skips it. An invalid value is ignored with a warning, and the default is used.
2. **`mitten-sleep` removed.** The parameter never reaches the server. All other query parameters, including a plain `sleep`, are forwarded.
3. **Matched against the mocks.** The query string is ignored when matching. If several mocks match, one is picked at random for each request.
4. **No match: passed through untouched.** The request goes to the server, and the server's response comes back unchanged.

### CORS

A browser only lets a page read a response from another origin (scheme, host and port) if the response has `Access-Control-Allow-Origin`. For most API calls it first sends an `OPTIONS` preflight, which must be answered with the right `Access-Control-Allow-*` headers. A short-circuited mock has no server to send those headers, so without help, mocked endpoints fail in the browser with CORS errors while real ones work.

| `mitten_cors` | Preflights | CORS headers added to |
|---|---|---|
| `off` | forwarded like any request | nothing |
| `mocks` (default) | answered by the addon when a mock would short-circuit the real request (same path, requested method) | short-circuited responses |
| `all` | all answered by the addon | every response, replacing the server's own CORS headers |

- A preflight is an `OPTIONS` request with `Origin` and `Access-Control-Request-Method`. The addon answers `204` allowing the requesting origin, the requested method and headers, and credentials. Any other `OPTIONS` request is matched against `OPTIONS` mocks as usual.
- The headers added to a response are `Access-Control-Allow-Origin` (the request's `Origin`, so cookies work), `Access-Control-Allow-Credentials: true`, `Access-Control-Expose-Headers` (all of the response's headers, so the page can read `Location` or `X-Mocked`) and `Vary: Origin`. Requests without `Origin` get none.
- With `mocks`, everything that reaches the server keeps the server's real CORS behaviour, so CORS mistakes in the backend still show.
- **Only use `all` locally.** It lets any website read every response through the proxy, with your cookies. Through a regular proxy that your browser uses for everything, that turns off the browser's protection for every site. mitmproxy logs a warning when it's set.
- Same-origin setups, such as a frontend dev server that proxies `/api`, never trigger CORS, so the option makes no difference there.

### Mock files

- **Which files load:** only files in `mock_dir` whose names start with `mitten-mock` and end in `.json`. Any other name, for example `x_mitten-mock-old.json`, is ignored, which is a way to turn a mock off.
- **When they load:** at startup, and when `mock_dir` changes. Editing a file does nothing until you run `:missingbe.reload`.
- **A broken file:** at startup mitmproxy stops with an error naming the file. On a reload, the error is shown and the previously loaded mocks stay active.
- **Several matching mocks:** the one with the most specific `path` wins: at the first segment where the patterns differ, a literal beats `:param`, which beats `:*`. Mocks with equally specific paths are variants, picked at random for every request. See [Path patterns](docs/mock-format.md#path-patterns).
- **`method` is required:** a method such as `"GET"`, or an array such as `["GET", "POST"]`, case-insensitive. A file without it fails to load.
- **`HEAD` requests use the `GET` mocks.** They get exactly what a GET would get (status, headers, `Content-Length` of the body), but never the body itself. A fall-through HEAD is forwarded to the server as HEAD. `HEAD` itself isn't allowed in `method`; a file with it fails to load.
- **No `request` part:** the request is forwarded to the server unchanged.
- **`request` with `statusCode`:** the proxy answers itself (short-circuit). The server is never contacted.
- **`statusCode`:** `404` is exact. `4` or `40` is a prefix: a random registered 4xx or 40x code, picked again for every request (1xx codes are never picked at random). An array such as `[200, 2, 503]` picks one element at random first. The reason phrase follows the code that was picked.
- **`request` without `statusCode`:** its headers and body are applied, then the request is forwarded to the server.
- **No `response` part:** the response, from the server or a short-circuit, is returned as it is.
- **`response` part:** only the fields it sets are changed. Status, headers and body it doesn't set keep their values.
- **Responses that can't have a body:** 1xx, 204, 205 and 304 responses are sent without a body even if the mock sets one, also when a `response` part adds a body to the server's own 304. A warning in the log names the mock file. Otherwise the client would read the leftover bytes as the start of the next response on the same connection.
- **`body`:** replaces the whole body, sent as JSON. `Content-Type` is set to `application/json; charset=utf-8` unless the part's `headers` set it. A short-circuit without `body` sends an empty body and no `Content-Type`.
- **`headers`:** each header replaces any existing header of the same name. A list gives one header line per value. A name or value starting with `_x_` is skipped.
- **Unknown fields:** ignored, with a warning in the log.

## Learn and test

Use the test server

```
    uv run python test-server.py
```

The test server then starts on localhost 3000. It answers GET/POST/PUT/PATCH/DELETE on two paths. `data` in the response is a dummy record for GET, the dummy with your JSON body merged in for PATCH, and your JSON body for POST and PUT:

- `/short-circuit`: the `mitten-mock-short-circuit-*.json` mocks in `example-responses/` answer these in the proxy, so they never reach the server.
- `/fall-through`: the `mitten-mock-fall-through-*.json` mocks alter the request and response, but the request is still forwarded to the server.

The server logs every request it receives (method, path with query, headers and body), so its log shows what got through the proxy.

Run the missing backend in front of the test server with the example mocks:

```
mitmproxy --mode reverse:http://localhost:3000 -s ./missingbe.py --set mock_dir=./example-responses --set connection_strategy=lazy -p 3001
```

The Bruno collection in `bruno/` has a request for each endpoint, and two environments: `Test server` (port 3000) and `Through mitmproxy` (port 3001). Each request has a disabled `mitten-sleep` query param; tick it in the Params tab to set that request's delay in the proxy.

## Mock files

Mocks are loaded from the `mitten-mock*.json` files in the directory given by the `mock_dir` option (default: the directory you start mitmproxy in):

```
mitmproxy --mode reverse:http://localhost:3000 -s ./missingbe.py --set mock_dir=./example-responses --set connection_strategy=lazy -p 3001
```

Changing the option while running (`:set mock_dir=./other-mocks`, or the options editor with `O`) loads that directory instead. After editing mock files, reload them with the command `:missingbe.reload`.

A mock matches on `path` and `method`. Its `request` part either answers the request directly (when it has a `statusCode`) or alters it before it goes to the server, and its `response` part alters the response:

```json
{
  "path": "/api/people/:id",
  "method": "GET",
  "request": { "statusCode": 200, "body": { "name": "Luke" } },
  "response": { "headers": { "X-Mocked": ["true"] } }
}
```

The full reference is in [docs/mock-format.md](docs/mock-format.md). What happens when a part or field is left out is listed under [Default behaviour](#default-behaviour).

## Code layout

- `missingbe.py`: the addon: its options and the request and response hooks.
- `mitten/`: the building blocks, one module per topic (mock files, path patterns, delays, responses, CORS, status codes).
- `tests/`: the tests, one file per topic. Run them with `uv run pytest -q`.

mitmproxy reloads `missingbe.py` when you save it, but not the modules in `mitten/`. Restart mitmproxy after editing those.

## Project docs

- [docs/mock-format.md](docs/mock-format.md): mock file reference
- [docs/adr/](docs/adr/): architecture decisions and why they were made
- [CHANGELOG.md](CHANGELOG.md): changes

## Create mocks

If you have a url you want to mock, you can get the started by fetching the data for it with:

```
curl -s -w "\n===\nstatus:%{http_code}\nmethod:%{method}\npath:%{url.path}\n" -X GET https://swapi.info/api/vehicles/14
```

the output can be piped to the util curl-2-mock to create a mock-bluprint. Note: curl-2-mock still generates the old `response` format.
