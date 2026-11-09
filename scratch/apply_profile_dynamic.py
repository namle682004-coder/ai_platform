import os

files = [
    "frontend/staff/profile.html",
    "frontend/console/profile.html",
    "frontend/dist/console/profile.html"
]

tab3_replacement = """          <!-- TAB 3: HẠN MỨC & API QUOTA -->
          <div id="tab-panel-quota" class="tab-panel space-y-6 hidden">
            <!-- Quota Metrics Cards -->
            <div class="grid grid-cols-1 sm:grid-cols-3 gap-5">
              <!-- Metric 1: Request Quota -->
              <div class="bg-white rounded-2xl border border-slate-200 shadow-card p-6">
                <div class="flex items-center justify-between">
                  <span class="text-xs font-bold uppercase tracking-wider text-slate-400">Monthly Calls</span>
                  <span class="w-8 h-8 rounded-lg bg-blue-50 text-blue-600 flex items-center justify-center text-sm">
                    <i class="fa-solid fa-arrow-trend-up"></i>
                  </span>
                </div>
                <div class="mt-3 flex items-baseline gap-2">
                  <span id="profile-quota-calls" class="text-2xl font-bold font-heading text-slate-900">...</span>
                  <span id="profile-quota-limit" class="text-xs text-slate-400">/ 100,000 reqs</span>
                </div>
                <div class="mt-3 w-full bg-slate-100 rounded-full h-2 overflow-hidden">
                  <div id="profile-quota-bar" class="bg-blue-600 h-2 rounded-full" style="width: 0%"></div>
                </div>
                <div class="mt-2 flex items-center justify-between text-[11px] text-slate-500">
                  <span id="profile-quota-pct">Đang tải...</span>
                  <span id="profile-quota-remain">Còn lại ...</span>
                </div>
              </div>

              <!-- Metric 2: Token Balance & Usage (Replaces fake GPU H100) -->
              <div class="bg-white rounded-2xl border border-slate-200 shadow-card p-6">
                <div class="flex items-center justify-between">
                  <span class="text-xs font-bold uppercase tracking-wider text-slate-400">Số Dư Token (Balance)</span>
                  <span class="w-8 h-8 rounded-lg bg-amber-50 text-amber-600 flex items-center justify-center text-sm">
                    <i class="fa-solid fa-coins"></i>
                  </span>
                </div>
                <div class="mt-3 flex items-baseline gap-2">
                  <span id="profile-token-balance" class="text-2xl font-bold font-heading text-slate-900">...</span>
                  <span id="profile-token-quota" class="text-xs text-slate-400">/ 50,000 Starter</span>
                </div>
                <div class="mt-3 w-full bg-slate-100 rounded-full h-2 overflow-hidden">
                  <div id="profile-token-bar" class="bg-amber-500 h-2 rounded-full" style="width: 100%"></div>
                </div>
                <div class="mt-2 flex items-center justify-between text-[11px] text-slate-500">
                  <span id="profile-token-spent">Đã dùng: 0 tokens</span>
                  <span class="text-emerald-600 font-semibold flex items-center gap-1"><i class="fa-solid fa-cloud"></i> MongoDB Atlas</span>
                </div>
              </div>

              <!-- Metric 3: Rate Limit Tier -->
              <div class="bg-white rounded-2xl border border-slate-200 shadow-card p-6">
                <div class="flex items-center justify-between">
                  <span class="text-xs font-bold uppercase tracking-wider text-slate-400">Rate Limit Tier</span>
                  <span class="w-8 h-8 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center text-sm">
                    <i class="fa-solid fa-gauge-high"></i>
                  </span>
                </div>
                <div class="mt-3">
                  <div class="text-2xl font-bold font-heading text-slate-900"><span id="profile-tier-rpm">1,200</span> <span class="text-xs font-normal text-slate-500">RPM</span></div>
                  <div id="profile-tier-name" class="text-xs text-indigo-600 font-semibold mt-0.5">Tier: Enterprise Developer</div>
                </div>
                <div class="mt-3 pt-2 border-t border-slate-100 flex items-center justify-between text-[11px] text-slate-500">
                  <span>Concurrency Max: 50 streams</span>
                  <a href="/staff/keys" class="text-primary-600 font-semibold hover:underline">Chi tiết &rarr;</a>
                </div>
              </div>
            </div>

            <!-- BẢNG MỚI: THEO DÕI TIÊU THỤ TOKEN & LƯỢT GỌI TỪNG API -->
            <div class="bg-white rounded-2xl border border-slate-200 shadow-card overflow-hidden">
              <div class="p-6 border-b border-slate-100 flex items-center justify-between">
                <div>
                  <h3 class="text-base font-bold text-slate-900 font-heading">Bảng Thống Kê Tiêu Thụ Token & Hạn Mức Từng API</h3>
                  <p class="text-xs text-slate-500 mt-0.5">Chi tiết số lượt gọi thực tế, số lỗi và lượng token tiêu thụ theo từng dịch vụ AI.</p>
                </div>
                <button
                  type="button"
                  onclick="loadProfileQuotaAndSummary()"
                  class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-100 text-slate-700 hover:bg-slate-200 transition-colors"
                >
                  <i class="fa-solid fa-rotate-right text-[10px]"></i> Làm mới dữ liệu
                </button>
              </div>

              <div class="overflow-x-auto">
                <table class="w-full text-left text-xs">
                  <thead class="bg-slate-50 text-slate-500 uppercase tracking-wider font-semibold border-b border-slate-200">
                    <tr>
                      <th class="px-6 py-3.5">Dịch vụ AI</th>
                      <th class="px-6 py-3.5">Endpoint</th>
                      <th class="px-6 py-3.5">Đơn giá Token</th>
                      <th class="px-6 py-3.5">Lượt gọi thực tế</th>
                      <th class="px-6 py-3.5">Lỗi</th>
                      <th class="px-6 py-3.5">Token đã trừ</th>
                      <th class="px-6 py-3.5">Hạn mức Free còn</th>
                      <th class="px-6 py-3.5">Trạng thái</th>
                    </tr>
                  </thead>
                  <tbody id="profile-api-consumption-tbody" class="divide-y divide-slate-100 text-slate-700">
                    <tr><td colspan="8" class="px-6 py-6 text-center text-slate-400"><i class="fa-solid fa-spinner fa-spin mr-2"></i>Đang tải dữ liệu tiêu thụ API...</td></tr>
                  </tbody>
                </table>
              </div>
            </div>

            <!-- API Keys Connected to this user -->
            <div class="bg-white rounded-2xl border border-slate-200 shadow-card overflow-hidden">
              <div class="p-6 border-b border-slate-100 flex items-center justify-between">
                <div>
                  <h3 class="text-base font-bold text-slate-900 font-heading">Khóa API được gán cho tài khoản này</h3>
                  <p class="text-xs text-slate-500 mt-0.5">Danh sách các API Key được tạo bởi hoặc phân quyền cho bạn.</p>
                </div>
                <a
                  href="/staff/keys"
                  class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-primary-50 text-primary-700 hover:bg-primary-100 transition-colors"
                >
                  <i class="fa-solid fa-plus text-[10px]"></i> Tạo Key mới
                </a>
              </div>

              <div class="overflow-x-auto">
                <table class="w-full text-left text-xs">
                  <thead class="bg-slate-50 text-slate-500 uppercase tracking-wider font-semibold border-b border-slate-200">
                    <tr>
                      <th class="px-6 py-3.5">Tên Key</th>
                      <th class="px-6 py-3.5">Mã Token Prefix</th>
                      <th class="px-6 py-3.5">Dự án</th>
                      <th class="px-6 py-3.5">Hạn mức / Tháng</th>
                      <th class="px-6 py-3.5">Trạng thái</th>
                      <th class="px-6 py-3.5 text-right">Thao tác</th>
                    </tr>
                  </thead>
                  <tbody id="profile-api-keys-tbody" class="divide-y divide-slate-100 text-slate-700">
                    <tr><td colspan="6" class="px-6 py-6 text-center text-slate-400"><i class="fa-solid fa-spinner fa-spin mr-2"></i>Đang tải danh sách API Keys...</td></tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>"""

js_code = """
      async function loadProfileQuotaAndSummary() {
        try {
          const headers = (window.getAuthHeaders && typeof window.getAuthHeaders === 'function') 
            ? window.getAuthHeaders() 
            : { 'Content-Type': 'application/json' };
          const res = await fetch('/v1/user/api-summary', { headers });
          if (!res.ok) return;
          const summary = await res.json();

          // 1. Quota Calls Card
          const totalCalls = Number(summary.total_requests) || 0;
          const monthlyLimit = Number(summary.monthly_limit) || 100000;
          const callsPct = Math.min(100, Math.round((totalCalls / monthlyLimit) * 1000) / 10);
          const callsRemain = Math.max(0, monthlyLimit - totalCalls);

          const callsEl = document.getElementById('profile-quota-calls');
          if (callsEl) callsEl.innerText = totalCalls.toLocaleString();
          const limitEl = document.getElementById('profile-quota-limit');
          if (limitEl) limitEl.innerText = `/ ${monthlyLimit.toLocaleString()} reqs`;
          const barEl = document.getElementById('profile-quota-bar');
          if (barEl) barEl.style.width = `${Math.max(1, callsPct)}%`;
          const pctEl = document.getElementById('profile-quota-pct');
          if (pctEl) pctEl.innerText = `Đã dùng ${callsPct}%`;
          const remainEl = document.getElementById('profile-quota-remain');
          if (remainEl) remainEl.innerText = `Còn lại ${callsRemain.toLocaleString()}`;

          // 2. Token Balance Card
          const paidBalance = Number(summary.paid_balance) || 0;
          const totalTokensUsed = Number(summary.total_tokens_used) || 0;
          const starterTotal = 50000;
          const tokenPct = Math.min(100, Math.round((paidBalance / starterTotal) * 100));

          const balEl = document.getElementById('profile-token-balance');
          if (balEl) balEl.innerText = paidBalance.toLocaleString();
          const tokenBarEl = document.getElementById('profile-token-bar');
          if (tokenBarEl) tokenBarEl.style.width = `${tokenPct}%`;
          const spentEl = document.getElementById('profile-token-spent');
          if (spentEl) spentEl.innerText = `Đã dùng: ${totalTokensUsed.toLocaleString()} tokens`;

          // 3. Rate Limit Tier Card
          const tierRpm = document.getElementById('profile-tier-rpm');
          if (tierRpm) tierRpm.innerText = (summary.rpm_limit || 1200).toLocaleString();
          const tierName = document.getElementById('profile-tier-name');
          if (tierName) tierName.innerText = `Tier: ${summary.tier || 'Enterprise Developer'}`;

          // 4. API Consumption Breakdown Table
          const tbody = document.getElementById('profile-api-consumption-tbody');
          if (tbody && Array.isArray(summary.data)) {
            if (summary.data.length === 0) {
              tbody.innerHTML = '<tr><td colspan="8" class="px-6 py-6 text-center text-slate-400">Chưa có dữ liệu gọi API</td></tr>';
              return;
            }
            tbody.innerHTML = summary.data.map(item => {
              const reqs = Number(item.requests) || 0;
              const errs = Number(item.errors) || 0;
              const rate = Number(item.token_rate) || 1;
              const tokens = Number(item.tokens_used) || (reqs * rate);
              const freeRemain = Number(item.free_remain) || 0;
              const fq = Number(item.free_quota) || 50000;
              const isExceeded = freeRemain <= 0;

              let icon = 'fa-cube';
              let iconBg = 'bg-blue-50 text-blue-600';
              if (item.path.includes('chat') || item.path.includes('rag')) {
                icon = 'fa-brain'; iconBg = 'bg-indigo-50 text-indigo-600';
              } else if (item.path.includes('audio') || item.path.includes('speech')) {
                icon = 'fa-microphone'; iconBg = 'bg-amber-50 text-amber-600';
              } else if (item.path.includes('ocr') || item.path.includes('vision')) {
                icon = 'fa-id-card'; iconBg = 'bg-emerald-50 text-emerald-600';
              } else if (item.path.includes('image')) {
                icon = 'fa-image'; iconBg = 'bg-rose-50 text-rose-600';
              }

              return `
                <tr class="hover:bg-slate-50 transition-colors">
                  <td class="px-6 py-3.5">
                    <div class="flex items-center gap-2.5">
                      <span class="w-7 h-7 rounded-lg ${iconBg} flex items-center justify-center text-xs flex-shrink-0">
                        <i class="fa-solid ${icon}"></i>
                      </span>
                      <div>
                        <div class="font-bold text-slate-900">${item.name}</div>
                        <div class="text-[10px] text-slate-400">${item.category}</div>
                      </div>
                    </div>
                  </td>
                  <td class="px-6 py-3.5 font-mono text-[11px] text-slate-600">${item.path}</td>
                  <td class="px-6 py-3.5">
                    <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold bg-amber-50 text-amber-700 border border-amber-200">
                      <i class="fa-solid fa-coins text-[9px]"></i> ${rate} tokens/call
                    </span>
                  </td>
                  <td class="px-6 py-3.5 font-semibold text-slate-900">${reqs.toLocaleString()}</td>
                  <td class="px-6 py-3.5">
                    ${errs > 0 
                      ? `<span class="inline-flex items-center px-1.5 py-0.5 rounded text-[11px] font-semibold bg-rose-50 text-rose-600">${errs.toLocaleString()}</span>`
                      : `<span class="text-slate-400">0</span>`}
                  </td>
                  <td class="px-6 py-3.5 font-semibold text-indigo-700 font-mono">${tokens.toLocaleString()}</td>
                  <td class="px-6 py-3.5 text-slate-600">${freeRemain.toLocaleString()} <span class="text-[10px] text-slate-400">/ ${fq.toLocaleString()}</span></td>
                  <td class="px-6 py-3.5">
                    ${isExceeded 
                      ? `<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold bg-rose-100 text-rose-800"><i class="fa-solid fa-triangle-exclamation text-[9px]"></i> Hết hạn</span>`
                      : `<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold bg-emerald-100 text-emerald-800"><i class="fa-solid fa-circle-check text-[9px]"></i> Sẵn sàng</span>`}
                  </td>
                </tr>
              `;
            }).join('');
          }
        } catch (err) {
          console.error('loadProfileQuotaAndSummary error:', err);
        }
      }

      async function loadProfileApiKeys() {
        const tbody = document.getElementById("profile-api-keys-tbody");
        if (!tbody) return;
        try {
          const headers = (window.getAuthHeaders && typeof window.getAuthHeaders === 'function') ? window.getAuthHeaders() : { 'Content-Type': 'application/json' };
          const res = await fetch("/v1/user/api-keys", { headers });
          if (!res.ok) throw new Error("Failed to fetch keys");
          const keys = await res.json();
          if (!Array.isArray(keys) || keys.length === 0) {
            tbody.innerHTML = `<tr><td colspan="6" class="px-6 py-6 text-center text-slate-400">Chưa có API Key nào được tạo. Nhấn "Tạo Key mới" để bắt đầu.</td></tr>`;
            return;
          }
          tbody.innerHTML = keys.map(k => {
            const isActive = k.status === 'active';
            const prefix = k.prefix || (k.key_value ? k.key_value.substring(0, 16) + '...' : 'aip_live_...');
            const rpm = k.rate_limit_rpm || 120;
            const tpm = k.rate_limit_tpm ? `${k.rate_limit_tpm.toLocaleString()} TPM` : '60k TPM';
            return `
              <tr class="hover:bg-slate-50/70 transition-colors">
                <td class="px-6 py-4 font-semibold text-slate-900 flex items-center gap-2">
                  <i class="fa-solid fa-key ${isActive ? 'text-amber-500' : 'text-slate-400'}"></i>
                  <span>${k.name || 'API Key'}</span>
                </td>
                <td class="px-6 py-4 font-mono text-slate-500">${prefix}</td>
                <td class="px-6 py-4">${k.project_name || 'Mặc định'}</td>
                <td class="px-6 py-4 font-medium text-slate-700">${rpm} RPM • ${tpm}</td>
                <td class="px-6 py-4">
                  <span class="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold ${isActive ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-100 text-slate-600'}">
                    ${isActive ? 'Active' : 'Disabled'}
                  </span>
                </td>
                <td class="px-6 py-4 text-right">
                  <a href="/staff/keys" class="text-primary-600 hover:text-primary-800 font-semibold">Quản lý</a>
                </td>
              </tr>
            `;
          }).join("");
        } catch (e) {
          console.error("Error loading profile keys:", e);
          tbody.innerHTML = `<tr><td colspan="6" class="px-6 py-4 text-center text-red-500">Không thể tải danh sách API Key</td></tr>`;
        }
      }

      async function refreshAuditLogs() {
        const listEl = document.getElementById("profile-audit-trail-list");
        if (!listEl) return;
        try {
          const res = await fetch("/v1/user/api-report?page=1&page_size=6");
          if (!res.ok) throw new Error("Failed to load audit logs");
          const json = await res.json();
          const logs = json.data || [];
          if (logs.length === 0) {
            listEl.innerHTML = `<p class="text-xs text-slate-400 pl-6 py-4">Chưa có nhật ký hoạt động gần đây.</p>`;
            return;
          }
          listEl.innerHTML = logs.map(l => {
            const isOk = (l.status_code >= 200 && l.status_code < 300);
            const dotColor = isOk ? 'bg-emerald-500' : 'bg-amber-500';
            const timeStr = l.timestamp ? new Date(l.timestamp).toLocaleString('vi-VN', { hour: '2-digit', minute: '2-digit', day: '2-digit', month: '2-digit' }) : 'Vừa xong';
            return `
              <div class="relative pl-6">
                <div class="absolute -left-[9px] top-1 w-4 h-4 rounded-full ${dotColor} border-2 border-white shadow"></div>
                <div class="flex items-center justify-between">
                  <span class="text-xs font-bold text-slate-900">${l.method || 'POST'} ${l.path || '/v1/inference'} (${l.status_code || 200})</span>
                  <span class="text-[11px] text-slate-400">${timeStr}</span>
                </div>
                <p class="text-xs text-slate-600 mt-1">IP: ${l.client_ip || '127.0.0.1'} • Latency: ${l.latency_ms || 0}ms • Prefix: <code>${l.api_key_prefix || 'Session'}</code></p>
              </div>
            `;
          }).join("");
        } catch (e) {
          console.error("Failed to load audit logs:", e);
        }
      }
"""

for fpath in files:
    if not os.path.exists(fpath):
        continue
    with open(fpath, "r", encoding="utf-8") as f:
        content = f.read()

    # Find the start of TAB 3 and end of TAB 3
    start_tag = "<!-- TAB 3: HẠN MỨC & API QUOTA -->"
    end_tag = "<!-- TAB 4: NHẬT KÝ HOẠT ĐỘNG (AUDIT LOGS) -->"
    if start_tag in content and end_tag in content:
        before = content.split(start_tag)[0]
        after = content.split(end_tag)[1]
        content = before + tab3_replacement + "\n\n          " + end_tag + after

    # Inject js_code before "// Initialize on load"
    if "async function loadProfileQuotaAndSummary()" not in content:
        init_marker = "// Initialize on load"
        if init_marker in content:
            content = content.replace(init_marker, js_code + "\n      " + init_marker)

    # In switchProfileTab, trigger loaders
    old_switch = """        const activeBtn = document.getElementById(`tab-btn-${tabId}`);
        if (activeBtn) {
          activeBtn.className = 'profile-tab-btn flex-1 min-w-[140px] px-4 py-2.5 rounded-lg text-xs font-semibold flex items-center justify-center gap-2 transition-all bg-primary-500 text-white shadow-sm';
        }"""
    new_switch = """        const activeBtn = document.getElementById(`tab-btn-${tabId}`);
        if (activeBtn) {
          activeBtn.className = 'profile-tab-btn flex-1 min-w-[140px] px-4 py-2.5 rounded-lg text-xs font-semibold flex items-center justify-center gap-2 transition-all bg-primary-500 text-white shadow-sm';
        }

        if (tabId === 'quota') {
          loadProfileQuotaAndSummary();
          loadProfileApiKeys();
        } else if (tabId === 'audit') {
          refreshAuditLogs();
        }"""
    if old_switch in content and "if (tabId === 'quota')" not in content:
        content = content.replace(old_switch, new_switch)

    # In DOMContentLoaded, call loaders
    old_dom = """      // Initialize on load
      document.addEventListener('DOMContentLoaded', () => {
        loadUserData();
      });"""
    new_dom = """      // Initialize on load
      document.addEventListener('DOMContentLoaded', () => {
        loadUserData();
        loadProfileQuotaAndSummary();
        loadProfileApiKeys();
        refreshAuditLogs();
      });"""
    if old_dom in content:
        content = content.replace(old_dom, new_dom)

    with open(fpath, "w", encoding="utf-8") as f:
        f.write(content)
    print("Successfully updated", fpath)


