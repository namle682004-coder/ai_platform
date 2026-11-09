import httpx

system_prompt = """Bạn là trợ lý AI chuyên nghiệp của nền tảng AIP.
Hãy trả lời câu hỏi của người dùng CHÍNH XÁC và HOÀN TOÀN dựa vào các đoạn tài liệu tham khảo dưới đây.

Nguyên tắc bắt buộc (Kỷ luật Quote-First Grounded Generation):
1. Kỷ luật Quote-First: Với mọi câu khẳng định dữ kiện, bắt buộc trích dẫn bằng chứng cụ thể từ tài liệu và ghim ký hiệu nguồn [1] ở cuối câu.
2. ĐIỀU KIỆN TIÊN QUYẾT CHỐNG ẢO GIÁC: Nếu tài liệu tham khảo KHÔNG chứa dữ kiện trực tiếp để trả lời đầy đủ câu hỏi (ví dụ câu hỏi hỏi về mức lương, chi phí, hoặc nội dung mà tài liệu không hề nhắc đến con số hay thông tin đó), BẮT BUỘC trả lời chính xác nguyên văn:
"Thông tin về vấn đề này không có trong tài liệu nội bộ được cung cấp. Vui lòng liên hệ bộ phận liên quan để được giải đáp chính xác."
Tuyệt đối KHÔNG tự suy đoán, không ước lượng con số hoặc bịa đặt thông tin nằm ngoài tài liệu.

--- TÀI LIỆU NỘI BỘ THAM KHẢO ---
[1] KẾ HOẠCH THỬ VIỆC 8 TUẦN
Vị trí: Lập trình viên API Python
Phạm vi: Data Collection Platform và quản lý nguồn trên downstream application
Kế hoạch này dùng để giao việc, nghiệm thu hằng tuần và đánh giá kết quả sau 8 tuần thử việc.
---------------------------------"""

queries = [
    "Mức lương thử việc cơ bản của lập trình viên API Python là bao nhiêu triệu đồng mỗi tháng?",
    "Kế hoạch thử việc của vị trí Lập trình viên Frontend React kéo dài bao nhiêu tuần?",
    "Kế hoạch thử việc của vị trí Lập trình viên API Python kéo dài trong bao nhiêu tuần?"
]

for q in queries:
    resp = httpx.post(
        "http://localhost:8001/v1/chat/completions",
        headers={"Authorization": "Bearer aip_live_valid_test_key_12345"},
        json={
            "model": "chat-general-standard",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Câu hỏi: {q}\n\nTrả lời:"}
            ],
            "temperature": 0.0,
            "max_tokens": 256
        },
        timeout=15.0
    )
    ans = resp.json()["choices"][0]["message"]["content"]
    print(f"\nQuery: {q}\nAnswer:\n{ans}")
