import json
import os
import sys
import urllib.request

payload = {
    "query": "laptop for programming",
    "documents": [
        {"text": "MacBook Pro 16", "metadata": {"category": "tech", "price": 2500}},
        {"text": "Wooden chair", "metadata": {"category": "home", "price": 50}},
        {"text": "Dell XPS 15", "metadata": {"category": "tech", "price": 1800}},
    ],
    "top_n": 2,
    "jsonlogic_filter": {
        "and": [
            {"==": [{"var": "category"}, "tech"]},
            {"<": [{"var": "price"}, 2000]},
        ]
    },
}

def main() -> int:
    api_key = os.getenv("SES_API_KEY", "").strip()
    if not api_key:
        print("Set SES_API_KEY to a customer API key before running this script.", file=sys.stderr)
        return 2

    req = urllib.request.Request(
        "http://127.0.0.1:8001/v1/rerank",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": api_key},
    )
    try:
        response = urllib.request.urlopen(req)
        print("SUCCESS")
        print(json.loads(response.read().decode("utf-8")))
    except Exception as exc:
        print("ERROR", type(exc).__name__)
        if hasattr(exc, "read"):
            print(exc.read().decode("utf-8"))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
