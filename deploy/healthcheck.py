import os
from urllib.request import urlopen

with urlopen(
    "http://127.0.0.1:" + os.getenv("PORT", "8000") + "/healthz", timeout=4
) as response:
    if response.status != 200:
        raise SystemExit(1)
