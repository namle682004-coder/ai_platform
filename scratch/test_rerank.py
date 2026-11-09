import requests

payload = {
    "model": "bge-reranker-v2-m3",
    "query": "tỉnh cao bằng kết hợp làm dự án có những mục tiêu nào",
    "documents": [
        "họp ngày 3/10\ntỉnh cao bằng kết hợp làm dự án\n+ đánh giá cán bộ bằng kpi\n+ giải pháp vnpt\n+ phần mềm saas\n+ theo nghị định 335 366 sổ tay hướng dẫn bộ nội vụ\n+ 335 có 4 bước: nhân viên nộp bài tự yêu cầu chấm điểm : trưởng phòng chấm điểm\n+ đánh giá k chấp nhận mang tính chất gây suy giảm hiệu suất\n+ độ phức tạp trong quá trình nhập liệu lớn nhưng chất ượng đầu ra chưa đủ đáp ứng\n+ không có chất lượng thực chất trong quá trình đáng giá\n+ đánh giá công chức bằng văn bản"
    ]
}

res = requests.post("http://172.16.20.2:8012/v1/rerank", json=payload)
print("Status:", res.status_code)
print("Response:", res.json())

