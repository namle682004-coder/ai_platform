import urllib.request
import json
import urllib.error

try:
    req = urllib.request.Request(
        'http://localhost:8000/v1/auth/login', 
        method='POST', 
        headers={'Content-Type': 'application/json'}, 
        data=json.dumps({'email': 'asd@asd.com', 'password': 'wrong'}).encode('utf-8')
    )
    res = urllib.request.urlopen(req)
    print("SUCCESS:", res.read().decode('utf-8'))
except urllib.error.HTTPError as e:
    print("FAILED:", e.code, e.read().decode('utf-8'))
