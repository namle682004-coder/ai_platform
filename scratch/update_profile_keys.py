import os

files = [
    "frontend/staff/profile.html",
    "frontend/console/profile.html",
    "frontend/dist/console/profile.html"
]

for file_path in files:
    if not os.path.exists(file_path):
        continue
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 1. Replace hardcoded tbody in Tab 3 with id="profile-api-keys-tbody"
    old_table_section = """                  <tbody class="divide-y divide-slate-100 text-slate-700">
                    <tr class="hover:bg-slate-50/70 transition-colors">
                      <td class="px-6 py-4 font-semibold text-slate-900 flex items-center gap-2">
                        <i class="fa-solid fa-key text-amber-500"></i>
                        <span>RAG Chatbot Production</span>
                      </td>
                      <td class="px-6 py-4 font-mono text-slate-500">aip_sk_948f...982b</td>
                      <td class="px-6 py-4">Retail Banking AI</td>
                      <td class="px-6 py-4">50,000 reqs</td>
                      <td class="px-6 py-4">
                        <span class="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold bg-emerald-100 text-emerald-800">
                          Active
                        </span>
                      </td>
                      <td class="px-6 py-4 text-right">
                        <a href="/staff/keys" class="text-primary-600 hover:text-primary-800 font-semibold">Quản lý</a>
                      </td>
                    </tr>
                    <tr class="hover:bg-slate-50/70 transition-colors">
                      <td class="px-6 py-4 font-semibold text-slate-900 flex items-center gap-2">
                        <i class="fa-solid fa-key text-blue-500"></i>
                        <span>OCR CCCD Verification Test</span>
                      </td>
                      <td class="px-6 py-4 font-mono text-slate-500">aip_sk_110a...bc41</td>
                      <td class="px-6 py-4">eKYC Solution</td>
                      <td class="px-6 py-4">25,000 reqs</td>
                      <td class="px-6 py-4">
                        <span class="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold bg-emerald-100 text-emerald-800">
                          Active
                        </span>
                      </td>
                      <td class="px-6 py-4 text-right">
                        <a href="/staff/keys" class="text-primary-600 hover:text-primary-800 font-semibold">Quản lý</a>
                      </td>
                    </tr>
                    <tr class="hover:bg-slate-50/70 transition-colors">
                      <td class="px-6 py-4 font-semibold text-slate-900 flex items-center gap-2">
                        <i class="fa-solid fa-key text-slate-400"></i>
                        <span>STT Voice Dev Local</span>
                      </td>
                      <td class="px-6 py-4 font-mono text-slate-500">aip_sk_772e...19aa</td>
                      <td class="px-6 py-4">Voice AI</td>
                      <td class="px-6 py-4">10,000 reqs</td>
                      <td class="px-6 py-4">
                        <span class="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold bg-slate-100 text-slate-600">
                          Idle
                        </span>
                      </td>
                      <td class="px-6 py-4 text-right">
                        <a href="/staff/keys" class="text-primary-600 hover:text-primary-800 font-semibold">Quản lý</a>
                      </td>
                    </tr>
                  </tbody>"""

    new_table_section = """                  <tbody id="profile-api-keys-tbody" class="divide-y divide-slate-100 text-slate-700">
                    <tr><td colspan="6" class="px-6 py-6 text-center text-slate-400"><i class="fa-solid fa-spinner fa-spin mr-2"></i>Đang tải danh sách API Keys...</td></tr>
                  </tbody>"""

    # 2. Add dynamic loader functions before </script>
    dynamic_functions = """
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
            const prefix = k.prefix || (k.value ? k.value.substring(0, 14) + "..." : "aip_live_...");
            const isActive = (k.status || "enabled") === "enabled";
            const rpm = k.rpm_limit || 60;
            const tpm = k.tpm_limit ? Math.round(k.tpm_limit / 1000) + "k TPM" : "100k TPM";
            return `
              <tr class="hover:bg-slate-50/70 transition-colors">
                <td class="px-6 py-4 font-semibold text-slate-900 flex items-center gap-2">
                  <i class="fa-solid fa-key ${isActive ? 'text-amber-500' : 'text-slate-400'}"></i>
                  <span>${k.name || 'API Key'}</span>
                </td>
                <td class="px-6 py-4 font-mono text-slate-500">${prefix}</td>
                <td class="px-6 py-4">${k.project_name || 'Default Project'}</td>
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

    # 3. Give audit list an id
    old_audit_list = """              <!-- Timeline of Events -->
              <div class="relative border-l-2 border-slate-200 ml-4 space-y-6 py-2">"""
    new_audit_list = """              <!-- Timeline of Events -->
              <div id="profile-audit-trail-list" class="relative border-l-2 border-slate-200 ml-4 space-y-6 py-2">"""

    # 4. Trigger loaders in switchTab
    old_switch = """        tabButtons.forEach(btn => btn.classList.remove('active', 'border-primary-600', 'text-primary-700'));
        tabPanels.forEach(p => p.classList.add('hidden'));

        activeButton.classList.add('active', 'border-primary-600', 'text-primary-700');
        const activePanel = document.getElementById(activePanelId);
        if (activePanel) activePanel.classList.remove('hidden');"""

    new_switch = """        tabButtons.forEach(btn => btn.classList.remove('active', 'border-primary-600', 'text-primary-700'));
        tabPanels.forEach(p => p.classList.add('hidden'));

        activeButton.classList.add('active', 'border-primary-600', 'text-primary-700');
        const activePanel = document.getElementById(activePanelId);
        if (activePanel) activePanel.classList.remove('hidden');

        if (activePanelId === 'tab-panel-keys') loadProfileApiKeys();
        if (activePanelId === 'tab-panel-audit') refreshAuditLogs();"""

    # Normalize and replace
    c_norm = content.replace("\r\n", "\n")
    c_norm = c_norm.replace(old_table_section.replace("\r\n", "\n"), new_table_section.replace("\r\n", "\n"))
    c_norm = c_norm.replace(old_audit_list.replace("\r\n", "\n"), new_audit_list.replace("\r\n", "\n"))
    c_norm = c_norm.replace(old_switch.replace("\r\n", "\n"), new_switch.replace("\r\n", "\n"))

    # Add dynamic functions before </script>
    if "async function loadProfileApiKeys()" not in c_norm:
        c_norm = c_norm.replace("      // Initial Load", dynamic_functions + "\n      // Initial Load")
        c_norm = c_norm.replace("loadActiveSessions();", "loadActiveSessions();\n      loadProfileApiKeys();\n      refreshAuditLogs();")

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(c_norm)
    print(f"Updated {file_path}")

