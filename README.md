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

The Bruno collection in `bruno/` has a request for each endpoint, and two environments: `Test server` (port 3000) and `Through mitmproxy` (port 3001). Each request has a disabled `sleep` query param; tick it in the Params tab to delay that request in the proxy.

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

The full reference is in [docs/mock-format.md](docs/mock-format.md). Add `?sleep=<ms>` to any request to delay it.

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
