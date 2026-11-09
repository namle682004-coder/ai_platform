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

## Các lớp bảo vệ hiện có

| Lớp                                            | Ở đâu                                                                                                                                            | Tác dụng                                                                                    |
| ---------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------- |
| Giới hạn RAM cho từng model + tự khởi động lại | `models/aip-model@.service` (systemd, `MemoryMax`)                                                                                               | Model vượt giới hạn thì chỉ model đó bị tắt rồi tự bật lại, máy vẫn sống                    |
| earlyoom                                       | `install.sh`                                                                                                                                     | Khi RAM sắp hết, tắt model lớn nhất **trước khi** máy treo; không bao giờ đụng sshd/dockerd |
| Giới hạn RAM cho container                     | `docker-compose.server.yml` (`mem_limit`), `apply_container_limits.sh`                                                                           | Không container nào chiếm hết RAM của máy                                                   |
| Model chạy cấu hình nhẹ RAM                    | `models/chat.env`: `--no-mmap -ngl 99 --parallel 2 -c 16384`                                                                                     | Trọng số model nằm trên GPU, không giữ bản sao trong RAM                                    |
| Giới hạn đồng thời + tự ngắt                   | `solutions/rag/infrastructure/adapters/runtime_guard.py`                                                                                         | Tối đa 2 lời gọi chat cùng lúc; model lỗi 3 lần liên tiếp thì ngừng gọi 30 giây             |
| Không gửi lại khi timeout                      | `model_registry.post_json_with_retry`                                                                                                            | Server đang bận thì không bị gửi thêm yêu cầu                                               |
| Giới hạn lượt chat                             | `RAG_CHAT_MAX_INFLIGHT` (6), `RAG_CHAT_RATE_LIMIT_PER_MINUTE` (30 / tenant + IP), `RAG_CHAT_GLOBAL_RATE_LIMIT_PER_MINUTE` (20 cho toàn hệ thống) | Quá sức thì trả 503 "Hệ thống đang bận" kèm `Retry-After`, không xếp hàng vô hạn            |
| Kiểm tra trước khi deploy                      | `scripts/deploy_server.sh`                                                                                                                       | Ổ trống < 6 GB hoặc RAM < 1,5 GB thì không build; build cache được dọn sau mỗi lần deploy   |
| Bộ chấm tự lùi                                 | `benchmarks/rag`                                                                                                                                 | Hệ thống báo bận thì chờ; 5 câu lỗi liên tiếp thì dừng hẳn                                  |

## Cài đặt một lần (cần sudo, chạy trên server)

```bash
cd ~/aip/app                          # bản code đã deploy
sudo deploy/server/install.sh --dry-run   # xem trước các bước
sudo deploy/server/install.sh
deploy/server/health.sh               # kiểm tra lại
```

`install.sh` sẽ:

1. tắt các llama-server đang chạy tay, rồi chạy lại chúng bằng systemd;
2. cài earlyoom;
3. đặt giới hạn RAM cho các container;
4. thêm 2 GB swap (chỉ khi ổ còn ≥ 8 GB);
5. giới hạn dung lượng log.

## Kiểm tra hằng ngày

```bash
ssh msp 'bash -s' < deploy/server/health.sh       # exit 0 = ổn, 1 = cảnh báo, 2 = nghiêm trọng
ssh msp 'bash -s' < deploy/server/disk_report.sh  # cái gì đang chiếm ổ đĩa (không xoá gì)
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
   ./deploy/server/generate_internal_certs.sh
   ```

   Lệnh trên tạo Root CA (`cyber_ca.crt`) và chứng chỉ máy chủ (`cyber_internal.crt`) có SAN bao gồm: `rag.cyber.internal`, `*.cyber.internal`, `aip.cyber.internal`, `172.16.20.2`.

2. **Cấu hình DNS / Hosts máy trạm**:
   Thêm vào `C:\Windows\System32\drivers\etc\hosts` (Windows) hoặc `/etc/hosts` (Linux/Mac):

   ```
   172.16.20.2  rag.cyber.internal aip.cyber.internal
   ```

3. **Cài đặt Root CA vào máy người dùng để hiển thị ổ khóa xanh (Secure)**:
   - File CA: `deploy/server/certs/cyber_ca.crt`.
   - Windows: Nhấp đúp file → _Install Certificate_ → _Local Machine_ → _Trusted Root Certification Authorities_.
   - Sau đó truy cập `https://rag.cyber.internal` trình duyệt sẽ xác thực bảo mật 100%.

## Giới hạn còn lại

- **Hai bản RAG cùng gọi một server model** (bản trên server và bản chạy ở máy dev) **có giới hạn riêng của từng bản**. Giới hạn chung thật sự nằm ở `--parallel 2` của llama-server cùng với giới hạn RAM của systemd.
- **8 GB RAM vẫn là nút thắt.** Các lớp trên biến tình huống "máy treo" thành "báo bận / tự khởi động lại model". Muốn phục vụ nhiều người hơn thì phải nâng RAM, hoặc tách các dịch vụ hạ tầng sang máy khác.
