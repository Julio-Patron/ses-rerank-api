import urllib.request
import json

payload = {
    "query": "laptop for programming",
    "documents": [
        {"text": "MacBook Pro 16", "metadata": {"category": "tech", "price": 2500}},
        {"text": "Wooden chair", "metadata": {"category": "home", "price": 50}},
        {"text": "Dell XPS 15", "metadata": {"category": "tech", "price": 1800}}
    ],
    "top_n": 2,
    "jsonlogic_filter": {
        "and": [
            {"==": [{"var": "category"}, "tech"]},
            {"<": [{"var": "price"}, 2000]}
        ]
    }
}

req = urllib.request.Request(
    'http://127.0.0.1:8001/v1/rerank',
    data=json.dumps(payload).encode('utf-8'),
    headers={'Content-Type': 'application/json', 'Authorization': 'Bearer test_admin_key_12345678901234567890'}
)
try:
    response = urllib.request.urlopen(req)
    print("SUCCESS")
    print(json.loads(response.read().decode('utf-8')))
except Exception as e:
    print("ERROR", e)
    if hasattr(e, 'read'):
        print(e.read().decode('utf-8'))
