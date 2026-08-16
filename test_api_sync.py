import urllib.request, json

# 1. POST
req = urllib.request.Request(
    'http://localhost:8000/v1/user/apis-state', 
    method='POST', 
    headers={'Content-Type': 'application/json'}, 
    data=json.dumps({'enabled_apis': {'Content Moderation API': True}}).encode('utf-8')
)
res = urllib.request.urlopen(req)
print("POST Response:", res.read().decode('utf-8'))

# 2. GET
res2 = urllib.request.urlopen('http://localhost:8000/v1/user/apis-state')
print("GET Response:", res2.read().decode('utf-8'))
