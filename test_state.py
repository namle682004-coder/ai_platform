import urllib.request, json

# 1. POST
req = urllib.request.Request('http://localhost:8000/v1/user/apis-state', method='POST', headers={'Content-Type': 'application/json'}, data=json.dumps({'enabled_apis': {'Content Moderation API': True}}).encode('utf-8'))
res = urllib.request.urlopen(req)
print("POST:", res.read().decode('utf-8'))

# 2. GET
req2 = urllib.request.Request('http://localhost:8000/v1/user/apis-state')
res2 = urllib.request.urlopen(req2)
print("GET:", res2.read().decode('utf-8'))
