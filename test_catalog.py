import urllib.request, json
res = urllib.request.urlopen('http://localhost:8000/v1/user/apis-catalog')
data = json.loads(res.read().decode('utf-8'))
for item in data:
    print(item.get('name'))
