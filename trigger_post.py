import urllib.request, json
req = urllib.request.Request(
    'http://localhost:8000/v1/user/apis-state', 
    method='POST', 
    headers={'Content-Type': 'application/json'}, 
    data=json.dumps({'enabled_apis': {'Speech to Text': True, 'Image Generation API': True}}).encode('utf-8')
)
try:
    urllib.request.urlopen(req)
    print("POST successful.")
except Exception as e:
    print("POST failed:", e)
