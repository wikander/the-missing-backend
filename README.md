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
