import requests

content = """họp ngày 3/10
tỉnh cao bằng kết hợp làm dự án
+ đánh giá cán bộ bằng kpi
+ giải pháp vnpt
  + phần mềm saas 
  + theo nghị định 335 366 sổ tay hướng dẫn bộ nội vụ
  + 335 có 4 bước: nhân viên nộp bài tự yêu cầu chấm điểm : trưởng phòng chấm điểm 
  + đánh giá k chấp nhận mang tính chất gây suy giảm hiệu suất
  + độ phức tạp trong quá trình nhập liệu lớn nhưng chất ượng đầu ra chưa đủ đáp ứng 
  + không có chất lượng thực chất trong quá trình đáng giá 
  + đánh giá công chức bằng văn bản
  + 2 loại danh mục sản phẩm : danh mục của nhân viên cán bộ tạo / quy đổi danh mục sản phẩm chuẩn  
  + vấn đề phát 1: sinh trong quá trình làm việc( việc đưa ra 1 danh mục chuẩn để so sánh là vấn đề chưa xử lí)
  + danh mục phân loại theo độ phức tạp(n1-n5)
  + chuyên giá đánh giá độ khó n1 =100...
  + vấn đề phát sinh 2: tại sao k tách ra những độ phức tạp ít hơn(n5 thành 5 mục n1 độ phức tạp ít hơn)
  +đánh  giá trên sản phẩm : số lượng, chất lượng, tiến độ thời gian
  + vấn đề khi đánh giá chất lượng công việc( trừ 25% mỗi lần gửi lại)mấy ông ni hay làm tay quen giờ trừ điểm k thích.
  + phức tạp trong quá trình phản hồi đánh giá 
  + vấn đề khi gửi lại trong quá trình nhập liệu sẽ *n lần phải nhập lại. tại vì yêu cầu sếp bắt làm lại
  + giao tiếp qua api nhưng dữ liệu k thay đổi
"""

with open("/tmp/hop_ngay_310.txt", "w", encoding="utf-8") as f:
    f.write(content)

files = {"file": ("hop_ngay_310.txt", open("/tmp/hop_ngay_310.txt", "rb"), "text/plain")}
data = {"title": "họp ngày 3/10 - Dự án tỉnh Cao Bằng", "department": "GENERAL"}
headers = {"Authorization": "Bearer aip_live_valid_test_key_12345"}

res = requests.post("http://172.16.20.2:8000/v1/knowledge/documents/upload?wait_for_completion=true", files=files, data=data, headers=headers)
print("Status:", res.status_code)
print("Response:", res.text)

