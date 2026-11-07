"""
A customer data source for the connector rehearsal (scripts/e2e_connectors.py), stdlib only (+ openpyxl).

  /api/posts?page=&limit=   JSON API behind a Bearer token: 42 social posts over three days
  /site/...                 a small intranet: a page with a merged-header table, a linked .xlsx, a logout link
  POST /_control            {"op": "reset" | "edit" | "drop_day" | "unlink_notes" | "down" | "up"}
  GET  /_control            what the crawler touched (e.g. whether /site/logout was ever requested)
"""

import argparse
import io
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

SENTIMENTS = ["Tích cực", "Trung tính", "Trung tính", "Tiêu cực", "Trung tính", "Trung tính", "Trung tính"]
TOKEN = os.getenv("FAKE_SOURCE_TOKEN", "demo-token")


def initial_posts():
    return [{
        "id": f"post-{i:03d}", "published_at": f"2026-11-0{1 + i // 14}T{8 + i % 10:02d}:00:00+07:00",
        "source": {"name": ["Báo A", "Báo B", "Trang C"][i % 3], "type": "news" if i % 3 < 2 else "fanpage"},
        "title": f"Bài viết số {i}", "sentiment": SENTIMENTS[i % 7], "tags": ["kinh tế", "địa phương"],
        "updated_at": f"2026-11-0{1 + i // 14}T20:00:{i % 60:02d}",
    } for i in range(42)]


STATE = {"posts": initial_posts(), "notes_linked": True, "down": False, "hits": []}


def xlsx_bytes():
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Chỉ tiêu"
    ws.append(["Đơn vị", "Chỉ tiêu", "Đạt"])
    for row in [("Phòng 1", 10, 9), ("Phòng 2", 8, 8), ("Phòng 3", 12, 7)]:
        ws.append(row)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def site(path):
    if path == "/site/index.html":
        notes = '<li><a href="notes.html">Ghi chú họp</a></li>' if STATE["notes_linked"] else ""
        return "text/html; charset=utf-8", f"""<html><head><title>Cổng thông tin nội bộ</title></head><body>
<nav><a href="/site/index.html">Trang chủ</a></nav><h1>Cổng thông tin nội bộ</h1>
<p>Tài liệu dùng chung của các phòng.</p>
<ul><li><a href="report.html">Báo cáo kết quả quý</a></li>{notes}
<li><a href="data/bang.xlsx">Bảng chỉ tiêu (Excel)</a></li><li><a href="/site/logout">Đăng xuất</a></li>
<li><a href="https://example.org/outside">Liên kết ngoài</a></li></ul><footer>Phòng CNTT</footer></body></html>"""
    if path == "/site/report.html":
        return "text/html; charset=utf-8", """<html><head><title>Báo cáo kết quả quý</title></head><body>
<h1>Báo cáo kết quả quý III</h1><p>Kết quả thực hiện theo đơn vị.</p>
<table><caption>Bảng 2. Kết quả theo đơn vị</caption>
<tr><th rowspan="2">Đơn vị</th><th colspan="2">Số lượng</th><th rowspan="2">Ghi chú</th></tr>
<tr><th>Kế hoạch</th><th>Thực hiện</th></tr>
<tr><td>Phòng 1</td><td>10</td><td>9</td><td></td></tr>
<tr><td>Phòng 2</td><td>8</td><td>8</td><td>Hoàn thành</td></tr>
<tr><td>Phòng 3</td><td>12</td><td>7</td><td>Chậm tiến độ</td></tr>
</table></body></html>"""
    if path == "/site/notes.html":
        return "text/html; charset=utf-8", "<h1>Ghi chú họp</h1><p>Họp giao ban thứ Hai hằng tuần lúc 8 giờ.</p>"
    if path == "/site/data/bang.xlsx":
        return "application/octet-stream", xlsx_bytes()  # as many servers send downloads; produced anew each time
    if path == "/site/logout":
        return "text/html; charset=utf-8", "<p>Đã đăng xuất</p>"
    return None


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else (body if isinstance(body, str) else json.dumps(body, ensure_ascii=False)).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):  # noqa: N802
        url = urlparse(self.path)
        if url.path == "/_control":
            return self._send(200, {"hits": STATE["hits"], "posts": len(STATE["posts"])})
        STATE["hits"].append(url.path)
        if STATE["down"]:
            return self._send(500, {"error": "maintenance"})
        if url.path == "/api/posts":
            if self.headers.get("Authorization") != f"Bearer {TOKEN}":
                return self._send(401, {"error": "unauthorized"})
            q = parse_qs(url.query)
            page, limit = int(q.get("page", ["1"])[0]), int(q.get("limit", ["10"])[0])
            rows = STATE["posts"][(page - 1) * limit: page * limit]
            return self._send(200, {"data": {"items": rows}, "total": len(STATE["posts"])})
        found = site(url.path)
        if not found:
            return self._send(404, {"error": "not found"})
        return self._send(200, found[1], found[0])

    def do_POST(self):  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        op = body.get("op")
        if op == "reset":
            STATE.update(posts=initial_posts(), notes_linked=True, down=False, hits=[])
        elif op == "edit":  # one post of 2026-11-02 changes sentiment at the source
            next(p for p in STATE["posts"] if p["id"] == "post-015").update(sentiment="Tích cực", updated_at="2026-11-05T10:00:00")
        elif op == "drop_day":  # the posts of 2026-11-03 are removed at the source
            STATE["posts"] = [p for p in STATE["posts"] if not p["published_at"].startswith("2026-11-03")]
        elif op == "unlink_notes":
            STATE["notes_linked"] = False
        elif op in ("down", "up"):
            STATE["down"] = op == "down"
        return self._send(200, {"ok": True, "op": op})

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8099)
    ThreadingHTTPServer(("0.0.0.0", ap.parse_args().port), Handler).serve_forever()
