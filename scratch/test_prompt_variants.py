import asyncio
import sys
sys.path.insert(0, "/home/namle/AI-Projects/llm-apps/ai_platform")

from solutions.rag.infrastructure.adapters.llm_adapter import HttpLlmAdapter

chunk11_text = """2.7. Tuần 7: Đo hiệu năng và kiểm soát sức khỏe danh mục nguồn Mục tiêu: Phân tích được một điểm nghẽn dựa trên số liệu, biết giới hạn mở rộng nguồn và duy trì dữ liệu vận hành đáng tin cậy. Mã Nhiệm vụ cụ thể Đầu ra và tiêu chí nghiệm thu A1 Chọn một nhóm nguồn/tác vụ có biểu hiện chậm hoặc tốn tài nguyên; đo thời gian thu thập/xử lý, độ trễ lịch chạy, mức đồng thời và tài nguyên theo khả năng quan sát thực tế Báo cáo có tập nguồn, khối lượng dữ liệu, cấu hình, khoảng đo và số lần đo; khoanh vùng điểm nghẽn bằng bằng chứng. Chỉ số chưa quan sát được được ghi rõ, không suy luận thành kết quả đo A2 Thử một điều chỉnh nhỏ có thể hoàn tác trên Test, hoặc kiểm chứng một phương án tối ưu; so sánh trên tải và điều kiện tương đương Có kết quả trước/sau và kiểm tra chất lượng dữ liệu/tỷ lệ lỗi."""

async def test_prompt_variants():
    llm = HttpLlmAdapter()
    
    # Baseline
    sys1 = (
        "Bạn là trợ lý AI chuyên nghiệp của nền tảng AIP.\n"
        "Hãy trả lời câu hỏi của người dùng CHÍNH XÁC và HOÀN TOÀN dựa vào các đoạn tài liệu tham khảo dưới đây.\n\n"
        "--- TÀI LIỆU NỘI BỘ THAM KHẢO ---\n"
        f"[1] (Tài liệu: Ke_hoach_thu_viec_API_Python_Developer.docx, Trang: 1)\n{chunk11_text}\n"
        "---------------------------------"
    )
    
    # Variant 2: Explicit alignment on code/identifier
    sys2 = (
        "Bạn là trợ lý AI chuyên nghiệp của nền tảng AIP.\n"
        "Hãy trả lời câu hỏi của người dùng CHÍNH XÁC và HOÀN TOÀN dựa vào các đoạn tài liệu tham khảo dưới đây.\n\n"
        "Nguyên tắc bắt buộc:\n"
        "1. Kỷ luật Quote-First: Luôn trích dẫn đúng dữ kiện từ tài liệu và ghi nguồn [1], [2] ở cuối câu.\n"
        "2. ĐỐI CHIẾU CHÍNH XÁC MÃ/MỤC: Khi tài liệu chứa bảng biểu hoặc danh sách mã (ví dụ: Mã A1, A2, B1, B2... hoặc Tuần 1, Tuần 2...), bạn BẮT BUỘC phải đọc kỹ và đối chiếu đúng mã được hỏi trong câu hỏi (ví dụ hỏi A2 thì trích xuất đúng dòng/mục của A2, TUYỆT ĐỐI không trích nhầm nội dung của mã khác như A1 hay B1).\n"
        "3. ĐIỀU KIỆN TIÊN QUYẾT CHỐNG ẢO GIÁC: Nếu câu hỏi hỏi về mã, danh mục hoặc dữ kiện KHÔNG CÓ trong tài liệu tham khảo (ví dụ hỏi nhiệm vụ A9 nhưng tài liệu chỉ có A1, A2), TUYỆT ĐỐI KHÔNG gán thông tin của mã khác vào, mà BẮT BUỘC trả lời chính xác nguyên văn: \"Thông tin về vấn đề này không có trong tài liệu nội bộ được cung cấp. Vui lòng liên hệ bộ phận liên quan để được giải đáp chính xác.\".\n\n"
        "--- TÀI LIỆU NỘI BỘ THAM KHẢO ---\n"
        f"[1] (Tài liệu: Ke_hoach_thu_viec_API_Python_Developer.docx, Trang: 1)\n{chunk11_text}\n"
        "---------------------------------"
    )
    
    for name, sys_p in [("Baseline", sys1), ("Variant 2 (Grounded Code & Anti-Hallucination)", sys2)]:
        print(f"\n==================== {name} ====================")
        res, _, _ = await llm.generate(
            messages=[
                {"role": "system", "content": sys_p},
                {"role": "user", "content": "Câu hỏi của người dùng: nhiệm vụ A2 của tuần 7 là gì vậy ?"}
            ],
            model="chat-general-standard",
            temperature=0.0,
            max_tokens=256
        )
        print("Q: nhiệm vụ A2 của tuần 7 là gì vậy ?")
        print("A:", res)
        
        res_a9, _, _ = await llm.generate(
            messages=[
                {"role": "system", "content": sys_p},
                {"role": "user", "content": "Câu hỏi của người dùng: nhiệm vụ A9 của tuần 7 là gì vậy ?"}
            ],
            model="chat-general-standard",
            temperature=0.0,
            max_tokens=256
        )
        print("\nQ: nhiệm vụ A9 của tuần 7 là gì vậy ?")
        print("A:", res_a9)

if __name__ == "__main__":
    asyncio.run(test_prompt_variants())
