import urllib.error
import urllib.request

url = "http://127.0.0.1:8000/api/v1/scan/start"
req = urllib.request.Request(url, method="POST", headers={"Content-Length": "0", "Accept": "application/json"})
try:
    with urllib.request.urlopen(req) as res:
        print("STATUS:", res.status)
        print("RESPONSE:", res.read().decode('utf-8'))
except urllib.error.URLError as e:
    print("ERROR:", e)
