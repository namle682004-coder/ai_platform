import urllib.request, json
req = urllib.request.Request('http://localhost:8000/v1/user/apis-state', method='POST', headers={'Content-Type': 'application/json'}, data=json.dumps({'enabled_apis': {'Speech to Text': False}}).encode('utf-8'))
urllib.request.urlopen(req)
res = urllib.request.urlopen('http://localhost:8000/v1/user/apis-state')
print(res.read().decode('utf-8'))
