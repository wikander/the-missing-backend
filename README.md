# The Missing Backend

If you should agree on something, agree on this.

to run: `mitmproxy --mode reverse:https://avtal-uppfoljning-dev.apps.tocp4.arbetsformedlingen.se -s ./missingbe.py --ssl-insecure -p 9999`

## Developing

Create an virtual environment

```
    python -m venv .venv
    source .venv/bin/activate
    python -m pip install -r requirements.txt
```

## Default behaviour

What the missing backend does when you don't configure anything.

### Options

| Option | Default | Meaning |
|---|---|---|
| `mock_dir` | `.` (the directory you start mitmproxy in) | Where `mitten-mock*.json` files are loaded from. |
| `mitten_default_sleep` | `[50,700]` | Delay in ms for requests without `?mitten-sleep=`. `0` turns it off. |

Set them with `--set name=value` on the command line, or `:set name=value` in mitmproxy.

### Every request through the proxy

1. **Delayed.** Each request waits a random 50–700 ms before anything else happens, whether a mock matches or not. `?mitten-sleep=500` (exactly 500 ms) or `?mitten-sleep=[200,800]` (random in that range) sets the delay for that request instead, and `?mitten-sleep=0` skips it. An invalid value is ignored with a warning, and the default is used.
2. **`mitten-sleep` removed.** The parameter never reaches the server. All other query parameters, including a plain `sleep`, are forwarded.
3. **Matched against the mocks.** The query string is ignored when matching. If several mocks match, one is picked at random for each request.
4. **No match: passed through untouched.** The request goes to the server, and the server's response comes back unchanged.

### Mock files

- **Which files load:** only files in `mock_dir` whose names start with `mitten-mock` and end in `.json`. Any other name, for example `x_mitten-mock-old.json`, is ignored, which is a way to turn a mock off.
- **When they load:** at startup, and when `mock_dir` changes. Editing a file does nothing until you run `:missingbe.reload`.
- **A broken file:** at startup mitmproxy stops with an error naming the file. On a reload, the error is shown and the previously loaded mocks stay active.
- **No `method`:** the mock matches every method.
- **No `request` part:** the request is forwarded to the server unchanged.
- **`request` with `statusCode`:** the proxy answers itself (short-circuit). The server is never contacted.
- **`request` without `statusCode`:** its headers and body are applied, then the request is forwarded to the server.
- **No `response` part:** the response, from the server or a short-circuit, is returned as it is.
- **`response` part:** only the fields it sets are changed. Status, headers and body it doesn't set keep their values.
- **`body`:** replaces the whole body, sent as JSON. `Content-Type` is set to `application/json; charset=utf-8` unless the part's `headers` set it. A short-circuit without `body` sends an empty body and no `Content-Type`.
- **`headers`:** each header replaces any existing header of the same name. A list gives one header line per value. A name or value starting with `_x_` is skipped.
- **Unknown fields:** ignored, with a warning in the log.

## Learn and test

Use the test server

```
    python test-server.py
```

The test server then starts on localhost 3000. It answers GET/POST/PUT/PATCH/DELETE on two paths. `data` in the response is a dummy record for GET, the dummy with your JSON body merged in for PATCH, and your JSON body for POST and PUT:

- `/short-circuit`: the `mitten-mock-short-circuit-*.json` mocks in `example-responses/` answer these in the proxy, so they never reach the server.
- `/fall-through`: the `mitten-mock-fall-through-*.json` mocks alter the request and response, but the request is still forwarded to the server.

The server logs every request it receives (method, path with query, headers and body), so its log shows what got through the proxy.

Run the missing backend in front of the test server with the example mocks:

```
mitmproxy --mode reverse:http://localhost:3000 -s ./missingbe.py --set mock_dir=./example-responses -p 3001
```

The Bruno collection in `bruno/` has a request for each endpoint, and two environments: `Test server` (port 3000) and `Through mitmproxy` (port 3001). Each request has a disabled `mitten-sleep` query param; tick it in the Params tab to set that request's delay in the proxy.

## Mock files

Mocks are loaded from the `mitten-mock*.json` files in the directory given by the `mock_dir` option (default: the directory you start mitmproxy in):

```
mitmproxy --mode reverse:http://localhost:3000 -s ./missingbe.py --set mock_dir=./example-responses -p 3001
```

Changing the option while running (`:set mock_dir=./other-mocks`, or the options editor with `O`) loads that directory instead. After editing mock files, reload them with the command `:missingbe.reload`.

A mock matches on `path` and optionally `method`. Its `request` part either answers the request directly (when it has a `statusCode`) or alters it before it goes to the server, and its `response` part alters the response:

```json
{
  "path": "/api/people/:id",
  "method": "GET",
  "request": { "statusCode": 200, "body": { "name": "Luke" } },
  "response": { "headers": { "X-Mocked": ["true"] } }
}
```

The full reference is in [docs/mock-format.md](docs/mock-format.md). What happens when a part or field is left out is listed under [Default behaviour](#default-behaviour).

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
