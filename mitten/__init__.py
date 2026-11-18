"""Building blocks for the missingbe.py addon, one module per topic.

- mock_file: the mitten-mock*.json format, parsed and validated.
- paths: path patterns, matching and specificity.
- sleep: delay values.
- responses: setting status, headers and bodies on mitmproxy messages.
- cors: CORS preflights and headers.
- http_status: status codes and reason phrases.

Nothing here keeps state or reads mitmproxy options; that is the addon's job.
"""
