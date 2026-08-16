import urllib.request, json
res = urllib.request.urlopen('http://localhost:8000/v1/user/apis-state')
print(res.read().decode('utf-8'))
