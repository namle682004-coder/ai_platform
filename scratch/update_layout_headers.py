import os

paths = [
    "frontend/staff/staff_layout.js",
    "frontend/shared/staff_layout.js",
    "frontend/assets/js/staff_layout.js",
    "frontend/public/assets/js/staff_layout.js"
]

for p in paths:
    if not os.path.exists(p):
        continue
    with open(p, "r", encoding="utf-8") as f:
        text = f.read()
    
    text = text.replace(
        "checkMandatoryAuth,\n        logoutUser,",
        "checkMandatoryAuth,\n        getAuthHeaders,\n        logoutUser,"
    )
    text = text.replace(
        "window.logoutUser = logoutUser;",
        "window.getAuthHeaders = getAuthHeaders;\n    window.logoutUser = logoutUser;"
    )
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"Updated {p}")

