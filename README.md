# The Missing Backend

If you should agree on something, agree on this.

to run: `mitmproxy --mode reverse:https://avtal-uppfoljning-dev.apps.tocp4.arbetsformedlingen.se -s ./missing_be.py --ssl-insecure -p 9999`

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

The test-server then start on localhost 3000. GET/POST/PUT/PATCH/DELETE request against http://localhost:3000/test, POST/PUT/PATCH accepts a josn body that is echoed back.

Run the missing backend in front of the test-server by running

```
mitmproxy --mode reverse:http://localhost:3000 -s ./missing_be.py --ssl-insecure -p 3001
```

## Create mocks

If you have a url you want to mock, you can get the started by fetching the data for it with:

```
curl -s -w "\n===\nstatus:%{http_code}\nmethod:%{method}\npath:%{url.path}\n" -X GET https://swapi.info/api/vehicles/14
```

the output can be piped to the util curl-2-mock to create a mock-bluprint.
