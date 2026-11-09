import glob

for pattern in ["frontend/**/*.html", "frontend/**/*.js"]:
    for f in glob.glob(pattern, recursive=True):
        data = open(f, "rb").read()
        if b"\r\n" in data:
            open(f, "wb").write(data.replace(b"\r\n", b"\n"))
            print("Normalized", f)
print("Done normalizing CRLF")

