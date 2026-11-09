# Vận hành server model (msp, 172.16.20.2)

## Sự cố ngày 05/11/2026

Khoảng 14:20 server bị treo cứng: mất SSH, mất ping, phải reset tay. Lúc 14:18 đọc được:

- RAM trống còn 97 MB trên 8 GB;
- load average 76;
- ổ `/` đầy 99%.

**Nguyên nhân:**

- Máy chỉ có 8 GB RAM nhưng chạy 3 model và 7 dịch vụ cùng lúc.
- Model 7B chạy với `-c 32768` và mmap, nên giữ ~81% RAM.
- Ổ đĩa gần đầy, máy không còn chỗ đệm khi thiếu RAM.
- Ứng dụng không giới hạn tải thật:
  - rate limit chat để 3000 request/phút;
  - không giới hạn số lời gọi model chạy cùng lúc;
  - gặp timeout thì tự gửi lại.

## Nâng cấp tài nguyên (Tháng 11/2026: 32 GB RAM)

Server đã được nâng cấp lên **32 GB RAM** (từ 8 GB trước đó) và trang bị GPU **NVIDIA TITAN Xp 12 GB VRAM**.
Cấu hình phân bổ RAM tối ưu cho 32 GB:
- **Model Runtimes (Systemd trên Host):** ~10 GB tối đa
  - `aip-model@chat` (Qwen2.5-7B, `--parallel 4`, `MemoryMax=5G`)
  - `aip-model@embedding` (bge-m3, `--parallel 4`, `MemoryMax=2.5G`)
  - `aip-model@rerank` (bge-reranker-v2-m3, `MemoryMax=2.5G`)
- **Docker Containers (App + Infra Stack):** ~12 GB tối đa
  - Qdrant: 2 GB | RAG API: 2 GB | RAG Worker: 1.5 GB | Gateway: 1 GB | LiteLLM: 1 GB | RabbitMQ: 1 GB | MinIO: 1 GB | Redis: 512 MB | Nginx: 128 MB
- **Dành cho OS, Page Cache, Disk I/O buffer:** ~10 GB an toàn.

## Tích hợp LiteLLM Model Gateway & Fallback Cloud (Gemini API)

Hệ thống bổ sung container `aip-litellm` (Port 4000) làm Gateway định tuyến model thông minh:
- **Ưu tiên 1:** Gọi Local Qwen2.5-7B (`chat-general-standard`) trên TITAN Xp.
- **Tự động Fallback:** Khi Local Model bị quá tải, lỗi 503/timeout hoặc đang bảo trì, LiteLLM tự động chuyển mạch mượt sang **Google Gemini 2.0 / 1.5 Flash (Free Tier API)** và **Gemini 1.5 Pro** mà không gây gián đoạn cho người dùng.

## Các lớp bảo vệ hiện có

| Lớp                                            | Ở đâu                                                                                                                                            | Tác dụng                                                                                    |
| ---------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------- |
| Giới hạn RAM cho từng model + tự khởi động lại | `models/aip-model@.service` (systemd, `MemoryMax`)                                                                                               | Model vượt giới hạn thì chỉ model đó bị tắt rồi tự bật lại, máy vẫn sống                    |
| earlyoom                                       | `install.sh`                                                                                                                                     | Khi RAM sắp hết, tắt model lớn nhất **trước khi** máy treo; không bao giờ đụng sshd/dockerd |
| Giới hạn RAM cho container                     | `docker-compose.server.yml` (`mem_limit`), `apply_container_limits.sh`                                                                           | Phân bổ tài nguyên hợp lý trên nền 32 GB RAM                                                |
| Model chạy cấu hình tối ưu VRAM/RAM            | `models/chat.env`: `--no-mmap -ngl 99 --parallel 4 -c 16384`                                                                                     | Trọng số model nằm trên GPU, 4 slot song song phục vụ đồng thời                             |
| LiteLLM Circuit Breaker & Fallback             | `deploy/onprem/compose/configs/litellm/litellm_config.yaml`                                                      | Tự ngắt mạch khi local model lỗi 2 lần liên tiếp, fallback sang Gemini API                  |
| Giới hạn đồng thời + tự ngắt                   | `solutions/rag/infrastructure/adapters/runtime_guard.py`                                                                                         | Tối đa 4 lời gọi chat cùng lúc; model lỗi 3 lần liên tiếp thì ngừng gọi 30 giây             |
| Không gửi lại khi timeout                      | `model_registry.post_json_with_retry`                                                                                                            | Server đang bận thì không bị gửi thêm yêu cầu                                               |
| Giới hạn lượt chat                             | `RAG_CHAT_MAX_INFLIGHT` (12), `RAG_CHAT_RATE_LIMIT_PER_MINUTE` (60 / tenant + IP), `RAG_CHAT_GLOBAL_RATE_LIMIT_PER_MINUTE` (60 cho toàn hệ thống) | Trả 503 "Hệ thống đang bận" kèm `Retry-After` khi quá tải                                    |
| Kiểm tra trước khi deploy                      | `scripts/deploy_server.sh`                                                                                                                       | Ổ trống < 6 GB hoặc RAM khả dụng < 3 GB thì dừng deploy                                     |
| Bộ chấm tự lùi                                 | `benchmarks/rag`                                                                                                                                 | Hệ thống báo bận thì chờ; 5 câu lỗi liên tiếp thì dừng hẳn                                  |

## Cài đặt một lần (cần sudo, chạy trên server)

```bash
cd ~/aip/app                          # bản code đã deploy
sudo deploy/onprem/host/scripts/install.sh --dry-run   # xem trước các bước
sudo deploy/onprem/host/scripts/install.sh
deploy/onprem/host/scripts/health.sh               # kiểm tra lại
```

`install.sh` sẽ:

1. tắt các llama-server đang chạy tay, rồi chạy lại chúng bằng systemd;
2. cài earlyoom;
3. đặt giới hạn RAM cho các container;
4. thêm 2 GB swap (chỉ khi ổ còn ≥ 8 GB);
5. giới hạn dung lượng log.

## Kiểm tra hằng ngày

```bash
ssh msp 'bash -s' < deploy/onprem/host/scripts/health.sh       # exit 0 = ổn, 1 = cảnh báo, 2 = nghiêm trọng
ssh msp 'bash -s' < deploy/onprem/host/scripts/disk_report.sh  # cái gì đang chiếm ổ đĩa (không xoá gì)
curl -s http://172.16.20.2:8010/health            # trạng thái quá tải của RAG ("load")
```

## Khi server không phản hồi

1. Ping và SSH đều không được, tức máy đã treo: cần reset tay. Sau khi cài `install.sh`, các model tự bật lại.
2. Sau khi máy lên, đọc log để biết nguyên nhân:
   - `journalctl -k -b -1 | grep -i -E "out of memory|oom"` (lần khởi động trước);
   - `journalctl -u earlyoom -b -1`.
3. Chạy `health.sh`, sửa các mục báo `CRITICAL` trước khi mở lại cho người dùng.

## Cấu hình HTTPS nội bộ (https://rag.cyber.internal)

Hệ thống hỗ trợ Reverse Proxy Nginx chạy trên port 80/443, trỏ về `aip-gateway:8000`:

1. **Khởi tạo chứng chỉ SSL Root CA & Wildcard**:

   ```bash
   ./deploy/onprem/host/scripts/generate_internal_certs.sh
   ```

   Lệnh trên tạo Root CA (`cyber_ca.crt`) và chứng chỉ máy chủ (`cyber_internal.crt`) có SAN bao gồm: `rag.cyber.internal`, `*.cyber.internal`, `aip.cyber.internal`, `172.16.20.2` được lưu trực tiếp vào `deploy/onprem/compose/configs/certs/`.

2. **Cấu hình DNS / Hosts máy trạm**:
   Thêm vào `C:\Windows\System32\drivers\etc\hosts` (Windows) hoặc `/etc/hosts` (Linux/Mac):

   ```
   172.16.20.2  rag.cyber.internal aip.cyber.internal
   ```

3. **Cài đặt Root CA vào máy người dùng để hiển thị ổ khóa xanh (Secure)**:
   - File CA: `deploy/onprem/compose/configs/certs/cyber_ca.crt`.
   - Windows: Nhấp đúp file → _Install Certificate_ → _Local Machine_ → _Trusted Root Certification Authorities_.
   - Sau đó truy cập `https://rag.cyber.internal` trình duyệt sẽ xác thực bảo mật 100%.

## Giới hạn & Điểm lưu ý sau khi lên 32 GB RAM

- **Khả năng phục vụ đồng thời:** Với `--parallel 4` trên Local llama-server và 12 inflight turns trong RAG, hệ thống đáp ứng mượt mà 4-10 người dùng chat đồng thời.
- **Khi vượt ngưỡng đồng thời:** LiteLLM tự động chuyển tiếp phần tải dôi dư sang **Gemini 2.0 / 1.5 Flash (Cloud)**, loại bỏ triệt để hiện tượng xếp hàng chờ nghẽn cổ chai.
- **Lưu ý hạn mức Gemini Free Tier:** Google AI Studio giới hạn 15 RPM (Request/phút). Cấu hình LiteLLM có `num_retries: 2` và fallback phụ trợ sang Gemini Pro để đảm bảo tính liên tục của dịch vụ.
