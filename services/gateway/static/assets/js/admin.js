// admin.js - AIP Admin Console Shared JavaScript
// Extracted from monolithic admin_dashboard.html for multi-page architecture

let isSignupMode = false;
let isCbActive = false;
let apiKeysData = [];
let pendingRequestsData = [];
let usersData = [];
let aliasesData = {};
let endpointsData = {};
let auditLogsData = [];

// ─── Modal Helpers ───────────────────────────────────────────────
function openModal(id) { document.getElementById(id).classList.add('active'); }
function closeModal(id) { document.getElementById(id).classList.remove('active'); }

// ─── Circuit Breaker Toggle ─────────────────────────────────────
async function toggleCircuitBreaker() {
    isCbActive = !isCbActive;
    const res = await fetch('/admin/v1/maintenance/toggle', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ is_maintenance: isCbActive, reason: 'Admin Emergency Switch' })
    });
    document.getElementById('cb-label').innerText = isCbActive ? 'ON (ACTIVE)' : 'OFF';
    showToast(`Emergency Circuit Breaker set to ${isCbActive ? 'ON (System Blocked)' : 'OFF (Normal Operation)'}`, isCbActive ? 'warning' : 'success');
}

// ─── Toast Notifications ────────────────────────────────────────
function showToast(msg, type = 'info') {
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        container.style.cssText = 'position:fixed; top:24px; right:24px; z-index:10000; display:flex; flex-direction:column; gap:10px;';
        document.body.appendChild(container);
    }
    const toast = document.createElement('div');
    toast.style.cssText = 'min-width:300px; padding:14px 20px; border-radius:8px; color:#fff; font-size:13px; font-weight:600; display:flex; align-items:center; justify-content:space-between; gap:10px; box-shadow:0 10px 25px rgba(0,0,0,0.25); opacity:0.96;';
    toast.style.background = type === 'success' ? '#10b981' : (type === 'error' ? '#ef4444' : (type === 'warning' ? '#f59e0b' : '#00a4b8'));
    toast.innerHTML = `<span>${msg}</span><span style="cursor:pointer; margin-left:auto;" onclick="this.parentElement.remove()">&times;</span>`;
    container.appendChild(toast);
    setTimeout(() => { toast.remove(); }, 3500);
}

// ─── AI Playground ──────────────────────────────────────────────
async function runPlaygroundTest() {
    const alias = document.getElementById('pg-alias').value;
    const prompt = document.getElementById('pg-prompt').value;
    const output = document.getElementById('pg-output');
    output.innerText = 'Executing model inference request...';
    try {
        const res = await fetch('/v1/chat/completions', {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'Authorization': 'Bearer aip_live_test_key'},
            body: JSON.stringify({ model: alias, messages: [{role: 'user', content: prompt}] })
        });
        const data = await res.json();
        output.innerText = JSON.stringify(data, null, 2);
    } catch (err) {
        output.innerText = 'Error executing playground request: ' + err;
    }
}

// ─── Users & RBAC ───────────────────────────────────────────────
async function fetchUsers() {
    try {
        const res = await fetch('/admin/v1/users');
        const json = await res.json();
        usersData = json.data || [];
        renderUsersTable();
    } catch (err) { console.error('Failed to fetch users:', err); }
}

function renderUsersTable() {
    const tbody = document.getElementById('users-table-body');
    if (!tbody) return;
    if (usersData.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" style="text-align:center; color: var(--text-sub);">No users found.</td></tr>';
        return;
    }
    tbody.innerHTML = usersData.map(u => `
        <tr>
            <td><code>${u.user_id}</code></td>
            <td><strong>${u.email}</strong></td>
            <td>${u.full_name || 'N/A'}</td>
            <td><span style="color:var(--primary); font-weight:700;">${u.role.toUpperCase()}</span></td>
            <td><span style="color:${u.status === 'active' ? 'var(--emerald)' : 'var(--rose)'}; font-weight:700;">${u.status}</span></td>
            <td><button class="btn btn-sm btn-secondary" onclick="toggleUserLock('${u.user_id}', '${u.status}')"><i class="fa-solid fa-lock"></i> ${u.status === 'active' ? 'Lock' : 'Unlock'}</button></td>
        </tr>`).join('');
}

async function toggleUserLock(userId, currentStatus) {
    const newStatus = currentStatus === 'active' ? 'locked' : 'active';
    await fetch(`/admin/v1/users/${userId}/status`, {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ status: newStatus })
    });
    fetchUsers();
    fetchAuditLogs();
}

// ─── Auth Login / Signup ────────────────────────────────────────
function toggleAuthMode() {
    isSignupMode = !isSignupMode;
    document.getElementById('auth-title').innerText = isSignupMode ? 'Staff / Admin Signup' : 'Staff / Admin Login';
    document.getElementById('auth-signup-fields').style.display = isSignupMode ? 'block' : 'none';
    document.getElementById('auth-submit-btn').innerHTML = isSignupMode ? '<i class="fa-solid fa-user-plus"></i> Register Account' : '<i class="fa-solid fa-right-to-bracket"></i> Login';
    document.getElementById('auth-toggle-link').innerText = isSignupMode ? 'Already have an account? Login' : 'Need an account? Signup';
}

async function handleAuthSubmit(e) {
    e.preventDefault();
    const email = document.getElementById('auth-email').value;
    const password = document.getElementById('auth-password').value;
    if (isSignupMode) {
        const fullName = document.getElementById('auth-fullname').value;
        const role = document.getElementById('auth-role').value;
        const res = await fetch('/v1/auth/signup', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ email, password, full_name: fullName, role })
        });
        const data = await res.json();
        showToast(data.message, res.ok ? 'success' : 'error');
        toggleAuthMode();
    } else {
        const res = await fetch('/v1/auth/login', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ email, password })
        });
        const data = await res.json();
        if (res.ok) {
            showToast(`Login Successful! Welcome ${data.user.full_name || data.user.email}`, 'success');
            localStorage.setItem('aip_user_session', JSON.stringify(data.user));
            sessionStorage.removeItem('aip_user_session');
            closeModal('modal-auth');
            if (data.user.role !== 'admin') {
                alert('Tài khoản này có vai trò Staff/Developer, không có quyền Administrator. Đang chuyển hướng sang Staff Portal.');
                window.location.href = '/staff/dashboard';
            } else {
                setTimeout(() => { window.location.reload(); }, 600);
            }
        } else {
            showToast('Login Failed: ' + data.detail, 'error');
        }
    }
}

function checkAdminAuth() {
    const raw = localStorage.getItem('aip_user_session');
    if (!raw) {
        window.location.href = '/login?redirect=' + encodeURIComponent(window.location.pathname);
        return false;
    }
    try {
        const user = JSON.parse(raw);
        if (user.role !== 'admin') {
            alert(`Tài khoản hiện tại [${user.email || 'Staff'}] không có quyền Administrator. Đang chuyển hướng về trang Staff Portal.`);
            window.location.href = '/staff/dashboard';
            return false;
        }
        const emailEl = document.getElementById('user-display-email');
        const roleEl = document.getElementById('user-display-role');
        if (emailEl) emailEl.innerText = user.email || 'admin@company.com';
        if (roleEl) roleEl.innerText = 'Administrator';

        const card = document.querySelector('.user-profile-card');
        if (card) {
            const btn = card.querySelector('button');
            if (btn) {
                btn.innerHTML = '<i class="fa-solid fa-right-from-bracket"></i> Logout';
                btn.onclick = logoutAdmin;
            }
        }
        return true;
    } catch (e) {
        localStorage.removeItem('aip_user_session');
        window.location.href = '/login';
        return false;
    }
}

function logoutAdmin() {
    localStorage.removeItem('aip_user_session');
    sessionStorage.removeItem('aip_user_session');
    window.location.href = '/login';
}

// Đồng bộ đăng nhập/đăng xuất giữa tất cả các tab của trình duyệt
window.addEventListener('storage', (e) => {
    if (e.key === 'aip_user_session') {
        window.location.reload();
    }
});

// ─── API Keys ───────────────────────────────────────────────────
async function fetchAPIKeys() {
    try {
        const res = await fetch('/admin/v1/keys');
        const json = await res.json();
        apiKeysData = json.data || [];
        renderKeysTable();
    } catch (err) { console.error('Failed to fetch API keys:', err); }
}

function renderKeysTable() {
    const tbody = document.getElementById('keys-table-body');
    if (!tbody) return;
    if (apiKeysData.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" style="text-align:center; color: var(--text-sub);">No API Keys found in MongoDB Atlas.</td></tr>';
        return;
    }
    tbody.innerHTML = apiKeysData.map(k => `
        <tr>
            <td><code>${k.key_id}</code></td>
            <td><strong>${k.tenant_id}</strong></td>
            <td>${k.rpm_limit} req/min</td>
            <td>${(k.tpm_limit || 100000).toLocaleString()} tpm</td>
            <td>${k.concurrency_limit} conc</td>
            <td><span style="color: var(--emerald); font-weight: 700;">${k.status || 'enabled'}</span></td>
            <td><button class="btn btn-sm btn-primary" onclick="openQuotaModal('${k.key_id}', ${k.rpm_limit}, ${k.tpm_limit}, ${k.concurrency_limit})"><i class="fa-solid fa-sliders"></i> Quota</button></td>
        </tr>`).join('');
}

// ─── Pending Key Requests ───────────────────────────────────────
async function fetchPendingKeyRequests() {
    try {
        const res = await fetch('/admin/v1/key-requests');
        const json = await res.json();
        pendingRequestsData = json.data || [];
        renderPendingRequestsTable();
    } catch (err) { console.error('Failed to fetch pending requests:', err); }
}

function renderPendingRequestsTable() {
    const tbody = document.getElementById('key-requests-table-body');
    if (!tbody) return;
    if (pendingRequestsData.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" style="text-align:center; color: var(--emerald); font-weight: 600;"><i class="fa-solid fa-circle-check"></i> No pending API Key requests from Staff.</td></tr>';
        return;
    }
    tbody.innerHTML = pendingRequestsData.map(r => `
        <tr>
            <td><code>${r.request_id}</code></td>
            <td><strong>${r.tenant_id}</strong></td>
            <td>${r.requested_by}</td>
            <td>${r.justification}</td>
            <td>${r.rpm_limit} RPM / ${(r.tpm_limit || 100000).toLocaleString()} TPM</td>
            <td><button class="btn btn-sm btn-success" onclick="approveKeyRequest('${r.request_id}')"><i class="fa-solid fa-check"></i> Approve</button>
                <button class="btn btn-sm btn-danger" onclick="rejectKeyRequest('${r.request_id}')"><i class="fa-solid fa-xmark"></i> Reject</button></td>
        </tr>`).join('');
}

async function approveKeyRequest(reqId) {
    const res = await fetch(`/admin/v1/key-requests/${reqId}/approve`, { method: 'POST' });
    const data = await res.json();
    showToast(`Key Request Approved! Generated API Key: ${data.api_key_plaintext}`, 'success');
    fetchPendingKeyRequests();
    fetchAPIKeys();
    fetchAuditLogs();
}

async function rejectKeyRequest(reqId) {
    const reason = prompt('Enter rejection reason for Staff request:');
    if (!reason) return;
    await fetch(`/admin/v1/key-requests/${reqId}/reject`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ reason })
    });
    fetchPendingKeyRequests();
    fetchAuditLogs();
}

// ─── Audit Logs ─────────────────────────────────────────────────
async function fetchAuditLogs() {
    try {
        const res = await fetch('/admin/v1/audit-logs');
        const json = await res.json();
        auditLogsData = json.data || [];
        renderAuditLogsTable();
    } catch (err) { console.error('Failed to fetch audit logs:', err); }
}

function renderAuditLogsTable() {
    const tbody = document.getElementById('audit-table-body');
    if (!tbody) return;
    if (auditLogsData.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" style="text-align:center; color: var(--text-sub);">No Audit logs recorded yet.</td></tr>';
        return;
    }
    tbody.innerHTML = auditLogsData.map(l => `
        <tr>
            <td><code>${l.log_id}</code></td>
            <td style="font-size:12px; color:var(--text-sub);">${new Date(l.timestamp).toLocaleString()}</td>
            <td><strong>${l.actor}</strong></td>
            <td><span style="color:var(--primary); font-weight:700;">${l.action}</span></td>
            <td>${l.resource}</td>
            <td><code>${l.ip_address}</code></td>
            <td>${l.details}</td>
        </tr>`).join('');
}

// ─── Create Key ─────────────────────────────────────────────────
async function handleCreateKey(e) {
    e.preventDefault();
    const payload = {
        tenant_id: document.getElementById('input-tenant').value,
        rpm_limit: parseInt(document.getElementById('input-rpm').value),
        tpm_limit: parseInt(document.getElementById('input-tpm').value),
        concurrency_limit: parseInt(document.getElementById('input-conc').value)
    };
    const res = await fetch('/admin/v1/keys', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload)
    });
    const data = await res.json();
    showToast(`API Key Generated! Plaintext Key: ${data.api_key_plaintext}`, 'success');
    closeModal('modal-create-key');
    fetchAPIKeys();
    fetchAuditLogs();
}

function openQuotaModal(keyId, rpm, tpm, conc) {
    document.getElementById('edit-key-id').value = keyId;
    document.getElementById('edit-rpm').value = rpm;
    document.getElementById('edit-tpm').value = tpm;
    document.getElementById('edit-conc').value = conc;
    openModal('modal-update-quota');
}

async function handleUpdateQuota(e) {
    e.preventDefault();
    const keyId = document.getElementById('edit-key-id').value;
    const payload = {
        rpm_limit: parseInt(document.getElementById('edit-rpm').value),
        tpm_limit: parseInt(document.getElementById('edit-tpm').value),
        concurrency_limit: parseInt(document.getElementById('edit-conc').value)
    };
    await fetch(`/admin/v1/keys/${keyId}/quota`, {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload)
    });
    closeModal('modal-update-quota');
    fetchAPIKeys();
    fetchAuditLogs();
}

// ─── Model Aliases ──────────────────────────────────────────────
async function fetchAliases() {
    try {
        const res = await fetch('/admin/v1/aliases');
        const json = await res.json();
        aliasesData = json.data || {};
        renderAliasesTable();
    } catch (err) { console.error('Failed to fetch aliases:', err); }
}

function renderAliasesTable() {
    const tbody = document.getElementById('aliases-table-body');
    if (!tbody) return;
    const entries = Object.entries(aliasesData);
    if (entries.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" style="text-align:center; color: var(--text-sub);">No Model Aliases found in MongoDB Atlas.</td></tr>';
        return;
    }
    tbody.innerHTML = entries.map(([name, item]) => `
        <tr>
            <td><code>${name}</code></td>
            <td><strong>${item.model_name || 'Qwen3-8B'}</strong></td>
            <td><span style="color: var(--purple); font-weight: 600;">${item.runtime || 'vllm'}</span></td>
            <td>${item.min_vram_gb || 24} GB</td>
            <td><label class="switch"><input type="checkbox" ${item.status === 'enabled' ? 'checked' : ''} onchange="toggleAliasStatus('${name}', this.checked)"><span class="slider"></span></label></td>
        </tr>`).join('');
}

async function toggleAliasStatus(name, isChecked) {
    const status = isChecked ? 'enabled' : 'disabled';
    await fetch(`/admin/v1/aliases/${name}`, {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ status })
    });
    fetchAliases();
    fetchAuditLogs();
}

// ─── Endpoints ──────────────────────────────────────────────────
async function fetchEndpoints() {
    try {
        const res = await fetch('/admin/v1/endpoints');
        const json = await res.json();
        endpointsData = json.data || {};
        renderEndpointsTable();
    } catch (err) { console.error('Failed to fetch endpoints:', err); }
}

function renderEndpointsTable() {
    const tbody = document.getElementById('endpoints-table-body');
    if (!tbody) return;
    const entries = Object.entries(endpointsData);
    if (entries.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" style="text-align:center; color: var(--text-sub);">No Export Endpoints found in MongoDB Atlas.</td></tr>';
        return;
    }
    tbody.innerHTML = entries.map(([id, item]) => `
        <tr>
            <td><code>${id}</code></td>
            <td><strong>${item.path}</strong></td>
            <td><span style="color: var(--primary); font-weight: 700;">${item.method}</span></td>
            <td>${item.description}</td>
            <td><label class="switch"><input type="checkbox" ${item.status === 'enabled' ? 'checked' : ''} onchange="toggleEndpointStatus('${id}', this.checked)"><span class="slider"></span></label></td>
        </tr>`).join('');
}

async function toggleEndpointStatus(id, isChecked) {
    const status = isChecked ? 'enabled' : 'disabled';
    await fetch(`/admin/v1/endpoints/${id}`, {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ status })
    });
    fetchEndpoints();
    fetchAuditLogs();
}

// ─── GPU Health Monitor ─────────────────────────────────────────
async function updateGpuStatus() {
    try {
        const res = await fetch('/v1/user/gpu-status');
        if (res.ok) {
            const data = await res.json();
            const nameEl = document.getElementById('gpu-health-name');
            const vramTextEl = document.getElementById('gpu-health-vram-text');
            const vramBarEl = document.getElementById('gpu-health-vram-bar');
            const tempEl = document.getElementById('gpu-health-temp');
            const tempBadgeEl = document.getElementById('gpu-health-temp-badge');
            const utilEl = document.getElementById('gpu-health-util');
            const utilBadgeEl = document.getElementById('gpu-health-util-badge');
            const statusBadgeEl = document.getElementById('gpu-health-status-badge');

            if (!nameEl) return; // Not on dashboard page

            if (data.gpu_detected) {
                nameEl.innerText = data.name;
                nameEl.title = data.name;
                vramTextEl.innerText = `${data.vram_used_mb.toLocaleString()} / ${data.vram_total_mb.toLocaleString()} MB (${data.vram_percentage}%)`;
                vramBarEl.style.width = `${data.vram_percentage}%`;
                if (data.vram_percentage > 85) { vramBarEl.style.background = 'var(--rose)'; }
                else if (data.vram_percentage > 60) { vramBarEl.style.background = 'var(--amber)'; }
                else { vramBarEl.style.background = 'var(--primary)'; }
                tempEl.innerText = `${data.temperature_c}°C`;
                if (data.temperature_c > 82) {
                    tempBadgeEl.innerHTML = '<i class="fa-solid fa-temperature-arrow-up"></i> Critical Hot';
                    tempBadgeEl.style.background = 'var(--rose-light)'; tempBadgeEl.style.color = 'var(--rose)';
                } else if (data.temperature_c > 75) {
                    tempBadgeEl.innerHTML = '<i class="fa-solid fa-temperature-three-quarters"></i> Warm';
                    tempBadgeEl.style.background = 'var(--amber-light)'; tempBadgeEl.style.color = 'var(--amber)';
                } else {
                    tempBadgeEl.innerHTML = '<i class="fa-solid fa-temperature-half"></i> Normal';
                    tempBadgeEl.style.background = '#e0f2fe'; tempBadgeEl.style.color = '#0369a1';
                }
                utilEl.innerText = `Util: ${data.gpu_utilization_pct}% | Power: ${data.power_draw_w}W`;
                statusBadgeEl.innerHTML = '<i class="fa-solid fa-circle-check"></i> Connected';
                statusBadgeEl.style.background = 'var(--emerald-light)'; statusBadgeEl.style.color = 'var(--emerald)';
                if (utilBadgeEl) {
                    utilBadgeEl.innerHTML = '<i class="fa-solid fa-bolt"></i> Operational';
                    utilBadgeEl.style.background = 'var(--emerald-light)'; utilBadgeEl.style.color = 'var(--emerald)';
                }
            } else {
                nameEl.innerText = "No NVIDIA GPU Detected";
                vramTextEl.innerText = "N/A";
                vramBarEl.style.width = '0%';
                tempEl.innerText = "-°C";
                utilEl.innerText = "Util: -% | Power: -W";
                statusBadgeEl.innerHTML = '<i class="fa-solid fa-triangle-exclamation"></i> Disconnected';
                statusBadgeEl.style.background = 'var(--rose-light)'; statusBadgeEl.style.color = 'var(--rose)';
                if (utilBadgeEl) {
                    utilBadgeEl.innerHTML = '<i class="fa-solid fa-xmark"></i> Inactive';
                    utilBadgeEl.style.background = '#f1f5f9'; utilBadgeEl.style.color = '#475569';
                }
            }
        }
    } catch (err) { console.error("Failed to update GPU status:", err); }
}

// ─── Traffic Chart ──────────────────────────────────────────────
function initChart() {
    const canvas = document.getElementById('trafficChart');
    if (!canvas) return; // Not on dashboard page
    const ctx = canvas.getContext('2d');
    new Chart(ctx, {
        type: 'line',
        data: {
            labels: ['16:00', '16:05', '16:10', '16:15', '16:20', '16:25', '16:30'],
            datasets: [{
                label: 'Throughput (RPS)',
                data: [42, 55, 49, 64, 58, 62, 70],
                borderColor: '#2563eb',
                backgroundColor: 'rgba(37, 99, 235, 0.12)',
                fill: true,
                tension: 0.4
            }]
        },
        options: {
            responsive: true,
            plugins: { legend: { display: false } },
            scales: { x: { grid: { color: '#f1f5f9' } }, y: { grid: { color: '#f1f5f9' } } }
        }
    });
}

// ─── Page Initialization (Conditional per Page) ─────────────────
window.addEventListener('DOMContentLoaded', () => {
    // 1. Mandatory Admin Role Authentication Check
    if (!checkAdminAuth()) return;

    // Dashboard-specific: chart + GPU health
    if (document.getElementById('trafficChart')) {
        initChart();
        updateGpuStatus();
        setInterval(updateGpuStatus, 5000);
    }

    // Keys page
    if (document.getElementById('keys-table-body')) {
        fetchAPIKeys();
        fetchPendingKeyRequests();
    }

    // Users page
    if (document.getElementById('users-table-body')) {
        fetchUsers();
    }

    // Aliases page
    if (document.getElementById('aliases-table-body')) {
        fetchAliases();
    }

    // Endpoints page
    if (document.getElementById('endpoints-table-body')) {
        fetchEndpoints();
    }

    // Audit page
    if (document.getElementById('audit-table-body')) {
        fetchAuditLogs();
    }
});
