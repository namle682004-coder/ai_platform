import os

files = [
    "frontend/staff/dashboard.html",
    "frontend/console/dashboard.html",
    "frontend/dist/console/dashboard.html"
]

for file_path in files:
    if not os.path.exists(file_path):
        continue
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 1. Update fetch functions to include getRequestHeaders()
    old_fetch = """      async function fetchEnabledAPIsFromBackend() {
        const response = await fetch("/v1/user/apis-state");
        if (!response.ok) {
          throw new Error(`Unable to load API states (${response.status})`);
        }
        const data = await response.json();
        return data.enabled_apis || {};
      }

      async function fetchApiCatalogFromBackend() {
        const response = await fetch("/v1/user/apis-catalog");
        if (!response.ok) {
          throw new Error(`Unable to load API catalog (${response.status})`);
        }
        const catalog = await response.json();
        if (!Array.isArray(catalog)) {
          throw new Error("The API catalog response is invalid");
        }
        return catalog;
      }

      async function fetchPaidBalanceFromBackend() {
        const response = await fetch("/v1/user/balance");
        if (!response.ok) {
          throw new Error(`Unable to load API balance (${response.status})`);
        }
        const data = await response.json();
        return Number(data.paid_balance) || 0;
      }

      async function fetchApiUsageSummaryFromBackend() {
        const response = await fetch("/v1/user/api-summary");"""

    new_fetch = """      function getRequestHeaders() {
        if (window.getAuthHeaders && typeof window.getAuthHeaders === 'function') {
          return window.getAuthHeaders();
        }
        const raw = localStorage.getItem('aip_user_session');
        const h = { 'Content-Type': 'application/json' };
        if (raw) {
          try {
            const u = JSON.parse(raw);
            if (u.user_id) h['X-User-Id'] = u.user_id;
          } catch (e) {}
        }
        return h;
      }

      async function fetchEnabledAPIsFromBackend() {
        const response = await fetch("/v1/user/apis-state", { headers: getRequestHeaders() });
        if (!response.ok) {
          throw new Error(`Unable to load API states (${response.status})`);
        }
        const data = await response.json();
        return data.enabled_apis || {};
      }

      async function fetchApiCatalogFromBackend() {
        const response = await fetch("/v1/user/apis-catalog", { headers: getRequestHeaders() });
        if (!response.ok) {
          throw new Error(`Unable to load API catalog (${response.status})`);
        }
        const catalog = await response.json();
        if (!Array.isArray(catalog)) {
          throw new Error("The API catalog response is invalid");
        }
        return catalog;
      }

      async function fetchPaidBalanceFromBackend() {
        const response = await fetch("/v1/user/balance", { headers: getRequestHeaders() });
        if (!response.ok) {
          throw new Error(`Unable to load API balance (${response.status})`);
        }
        const data = await response.json();
        return Number(data.paid_balance) || 0;
      }

      async function fetchApiUsageSummaryFromBackend() {
        const response = await fetch("/v1/user/api-summary", { headers: getRequestHeaders() });"""

    # 2. Update renderDashboardRows calculation
    old_calc = """          const apiName = item.name || item.endpoint_id || item.path || "Unnamed API";
          const apiPath = item.path || item.endpoint_id;
          const usage = usageSummary?.[apiPath];
          const isEnabled = isApiActive(apis, apiName);
          const paidUnit =
            item.unit === "character" ? 1 : item.unit === "block" ? 150 : 10;
          const freeVal = item.free_quota
            ? item.free_quota.split(" ")[0]
            : "—";"""

    new_calc = """          const apiName = item.name || item.endpoint_id || item.path || "Unnamed API";
          const apiPath = item.path || item.endpoint_id;
          const usage = usageSummary?.[apiPath];
          const isEnabled = isApiActive(apis, apiName);
          const paidUnit =
            item.unit === "character" ? 1 : item.unit === "block" ? 150 : 10;
          const reqCount = Number(usage?.requests) || 0;
          const errCount = Number(usage?.errors) || 0;
          const freeQuotaLimit = item.free_quota ? (parseInt(item.free_quota.replace(/,/g, '')) || 1000) : 1000;
          const freeRemain = Math.max(0, freeQuotaLimit - reqCount);
          const freeVal = freeRemain.toLocaleString();"""

    old_row = """          const tr = document.createElement("tr");
          tr.innerHTML = `
                    <td><strong style="color: #007bff; cursor:pointer;" onclick="location.href='${svcUrl}'">${apiName}</strong></td>
                    <td>${statusBadge}</td>
                    <td>${usage?.requests ?? "—"}</td>
                    <td>${usage?.errors ?? "—"}</td>
                    <td>${isEnabled ? freeVal : "0 (OFF)"}</td>
                    <td>${paidStr}</td>
                    <td>${item.unit || "—"}</td>
                    <td><button class="btn-buy-link" onclick="openPricingModalFor('${apiName}')">buy more</button></td>
                `;"""

    new_row = """          if (nameLow.includes("rag") || nameLow.includes("tri thức")) {
            svcUrl = "/project/global/apis/rag-chat-enterprise-kb";
          }
          const tr = document.createElement("tr");
          tr.innerHTML = `
                    <td><strong style="color: #007bff; cursor:pointer;" onclick="location.href='${svcUrl}'">${apiName}</strong></td>
                    <td>${statusBadge}</td>
                    <td><span style="font-weight:600; color:#0f172a;">${reqCount}</span></td>
                    <td><span style="color:${errCount > 0 ? '#dc2626' : '#64748b'}; font-weight:${errCount > 0 ? '700' : '400'};">${errCount}</span></td>
                    <td><span style="color:#059669; font-weight:600;">${isEnabled ? freeVal : "0 (OFF)"}</span></td>
                    <td><span style="color:#2563eb; font-weight:600;">${paidStr}</span></td>
                    <td>${item.unit || "request"}</td>
                    <td><button class="btn-buy-link" onclick="openPricingModalFor('${apiName}')">buy more</button></td>
                `;"""

    content_norm = content.replace("\r\n", "\n")
    content_norm = content_norm.replace(old_fetch.replace("\r\n", "\n"), new_fetch.replace("\r\n", "\n"))
    content_norm = content_norm.replace(old_calc.replace("\r\n", "\n"), new_calc.replace("\r\n", "\n"))
    content_norm = content_norm.replace(old_row.replace("\r\n", "\n"), new_row.replace("\r\n", "\n"))

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content_norm)
    print(f"Updated {file_path}")

