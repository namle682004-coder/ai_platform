// --- MASTER LAYOUT & TOPBAR COMMON SCRIPT FOR EVERWIN AI PLATFORM STAFF PORTAL ---

const AIP_I18N = {
    en: {
        dashboard: "Dashboard",
        apis: "APIs",
        api_keys: "API Keys",
        api_report: "API report",
        payment_history: "Payment history",
        contact_us: "Contact us",
        console: "Console",
        applications: "Applications",
        speech_to_text: "Speech to Text",
        text_to_speech: "Text to Speech",
        llm_chatbot: "LLM Chatbot API",
        select_project: "Select a project",
        logout: "Logout",
        create_prepaid_project: "CREATE PREPAID PROJECT",
        search: "Search",
        payment_support: "Payment & Support",
        back_to_dashboard: "Back to Dashboard",
        back_to_apis: "Back to APIs Catalog",
        language: "English"
    },
    vi: {
        dashboard: "Bảng Điều Khiển",
        apis: "Danh Sách API",
        api_keys: "Quản Lý API Key",
        api_report: "Báo Cáo Sử Dụng",
        payment_history: "Lịch Sử Thanh Toán",
        contact_us: "Liên Hệ & Phản Hồi",
        console: "Bảng Điều Khiển",
        applications: "Ứng Dụng AI",
        speech_to_text: "Nhận Dạng Giọng Nói",
        text_to_speech: "Tổng Hợp Giọng Nói",
        llm_chatbot: "LLM Chatbot API",
        select_project: "Chọn Dự Án",
        logout: "Đăng Xuất",
        create_prepaid_project: "TẠO DỰ ÁN TRẢ TRƯỚC",
        search: "Tìm kiếm",
        payment_support: "Thanh toán & Hỗ trợ",
        back_to_dashboard: "Quay lại Bảng điều khiển",
        back_to_apis: "Quay lại Danh sách API",
        language: "Tiếng Việt"
    }
};

const AIP_COMMON_TRANSLATION_KEYS = {
    "Console": "console",
    "Bảng Điều Khiển": "console",
    "Bảng điều khiển": "console",
    "Applications": "applications",
    "Ứng Dụng AI": "applications",
    "Payment & Support": "payment_support",
    "Thanh toán & Hỗ trợ": "payment_support",
    "Dashboard": "dashboard",
    "APIs": "apis",
    "API Keys": "api_keys",
    "API report": "api_report",
    "Payment history": "payment_history",
    "Contact us": "contact_us",
    "Speech to Text": "speech_to_text",
    "Text to Speech": "text_to_speech",
    "LLM Chatbot": "llm_chatbot",
    "Select a project": "select_project",
    "Default Project": "select_project"
};

function getAppLanguage() {
    return localStorage.getItem('aip_lang') || 'en';
}

const aipSetLanguage = (lang) => {
    const nextLanguage = AIP_I18N[lang] ? lang : 'en';
    localStorage.setItem('aip_lang', nextLanguage);
    location.reload();
};

function setAppLanguage(lang) {
    aipSetLanguage(lang);
}

document.addEventListener('click', (event) => {
    const languageOption = event.target.closest('[onclick*="setAppLanguage("]');
    if (!languageOption) return;
    const match = languageOption.getAttribute('onclick').match(/setAppLanguage\(['"](en|vi)['"]\)/);
    if (!match) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    aipSetLanguage(match[1]);
}, true);

function translateCommonText(element, language) {
    if (!element) return;
    const sourceText = Array.from(element.childNodes)
        .filter(node => node.nodeType === Node.TEXT_NODE)
        .map(node => node.textContent.trim())
        .join(' ')
        .replace(/\s+/g, ' ')
        .trim();
    const key = AIP_COMMON_TRANSLATION_KEYS[sourceText];
    if (!key || !AIP_I18N[language][key]) return;

    const textNode = Array.from(element.childNodes).find(node => node.nodeType === Node.TEXT_NODE && node.textContent.trim());
    if (textNode) textNode.textContent = ` ${AIP_I18N[language][key]} `;
}

function applyCommonTranslations() {
    const language = getAppLanguage();
    const dictionary = AIP_I18N[language] || AIP_I18N.en;
    const languageLabel = document.getElementById('current-lang-text');
    const projectLabel = document.getElementById('current-project-label');
    if (languageLabel) languageLabel.textContent = dictionary.language;
    if (projectLabel && AIP_COMMON_TRANSLATION_KEYS[projectLabel.textContent.trim()]) {
        projectLabel.textContent = dictionary.select_project;
    }

    document.querySelectorAll('.sidebar .section-title, .sidebar .nav-item a').forEach(element => {
        translateCommonText(element, language);
    });

    document.querySelectorAll('[title="Back to Dashboard"], [title="Quay lại Bảng điều khiển"]').forEach(element => {
        element.title = dictionary.back_to_dashboard;
    });
    document.querySelectorAll('[title="Back to APIs Catalog"], [title="Quay lại Danh sách API"]').forEach(element => {
        element.title = dictionary.back_to_apis;
    });
}

function toggleLangDropdown(e) {
    if (e) e.stopPropagation();
    const menu = document.getElementById('lang-dropdown-menu');
    if (menu) {
        menu.style.display = menu.style.display === 'none' ? 'block' : 'none';
    }
}

document.addEventListener('click', function(e) {
    const menu = document.getElementById('lang-dropdown-menu');
    if (menu && !menu.contains(e.target)) {
        menu.style.display = 'none';
    }
});

async function getProjects() {
    try {
        const res = await fetch('/v1/user/projects');
        if (res.ok) {
            const data = await res.json();
            localStorage.setItem('aip_projects', JSON.stringify(data));
            return data;
        }
    } catch (err) {}
    const data = localStorage.getItem('aip_projects');
    return data ? JSON.parse(data) : [
        { project_id: 'proj_default', project_name: 'wwrwer23', created_at: '2026-08-16', type: 'prepaid' }
    ];
}

function toCanonicalApiName(name) {
    if (!name) return "";
    const trimmed = name.trim();
    const low = trimmed.toLowerCase();
    if (low.includes("speech to text")) return "Speech to Text API";
    if (low.includes("text to speech")) return "Text to Speech API";
    if (low.includes("llm") || low.includes("chatbot")) return "LLM Chatbot API";
    if (low.includes("image")) return "Image Generation API";
    if (low.includes("moderation")) return "Content Moderation API";
    return trimmed.endsWith(" API") ? trimmed : (trimmed + " API");
}

function getEnabledAPIs() {
    const data = localStorage.getItem('aip_enabled_apis');
    if (data) {
        try {
            const parsed = JSON.parse(data);
            const sanitized = {};
            for (const [k, v] of Object.entries(parsed)) {
                sanitized[toCanonicalApiName(k)] = Boolean(v);
            }
            return sanitized;
        } catch(e) {}
    }
    return {
        "Speech to Text API": true,
        "Text to Speech API": false,
        "LLM Chatbot API": false,
        "Image Generation API": false,
        "Content Moderation API": false
    };
}

async function fetchEnabledAPIsFromBackend() {
    try {
        const res = await fetch('/v1/user/apis-state?t=' + new Date().getTime());
        if (res.ok) {
            const data = await res.json();
            if (data && data.enabled_apis && Object.keys(data.enabled_apis).length > 0) {
                const sanitized = {};
                for (const [k, v] of Object.entries(data.enabled_apis)) {
                    sanitized[toCanonicalApiName(k)] = Boolean(v);
                }
                localStorage.setItem('aip_enabled_apis', JSON.stringify(sanitized));
                return sanitized;
            }
        }
    } catch(err) {}
    return getEnabledAPIs();
}

function isApiActive(apis, name) {
    if (!apis || !name) return false;
    const canon = toCanonicalApiName(name);
    if (apis[canon] !== undefined) return Boolean(apis[canon]);
    if (apis[name] !== undefined) return Boolean(apis[name]);
    return false;
}

async function setEnabledAPIs(apiObj) {
    const current = getEnabledAPIs();
    const cleanUpdated = { ...current };

    // Directly update only the canonical keys that changed
    for (const [key, val] of Object.entries(apiObj)) {
        cleanUpdated[toCanonicalApiName(key)] = Boolean(val);
    }

    localStorage.setItem('aip_enabled_apis', JSON.stringify(cleanUpdated));
    try {
        const res = await fetch('/v1/user/apis-state', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ enabled_apis: cleanUpdated })
        });
        if (res.ok) {
            const data = await res.json();
            if (data && data.enabled_apis) {
                const backendClean = {};
                for (const [k, v] of Object.entries(data.enabled_apis)) {
                    backendClean[toCanonicalApiName(k)] = Boolean(v);
                }
                localStorage.setItem('aip_enabled_apis', JSON.stringify(backendClean));
            }
        }
    } catch(err) {
        console.error("Failed to update API state on backend:", err);
    }
}

async function fetchApiCatalogFromBackend() {
    try {
        const res = await fetch('/v1/user/apis-catalog?t=' + new Date().getTime());
        if (res.ok) {
            const data = await res.json();
            localStorage.setItem('aip_catalog', JSON.stringify(data));
            return data;
        }
    } catch(err) {}
    const cached = localStorage.getItem('aip_catalog');
    return cached ? JSON.parse(cached) : [
        { name: "Speech to Text", unit: "block", free_quota: "10,000 blocks" },
        { name: "Text to Speech", unit: "character", free_quota: "100,000 characters" },
        { name: "LLM Chatbot API", unit: "token", free_quota: "50,000 tokens" },
        { name: "Image Generation API", unit: "image", free_quota: "100 images" },
        { name: "Content Moderation API", unit: "request", free_quota: "10,000 requests" }
    ];
}

function getActiveProjectName() {
    const active = localStorage.getItem('aip_active_project');
    if (active) return active;
    const rawProjs = localStorage.getItem('aip_projects');
    if (rawProjs) {
        try {
            const arr = JSON.parse(rawProjs);
            if (arr.length > 0) return arr[0].project_name;
        } catch(e) {}
    }
    return 'wwrwer23';
}

function getPaidBalance() {
    return parseInt(localStorage.getItem('aip_paid_balance') || '0');
}

function setPaidBalance(val) {
    localStorage.setItem('aip_paid_balance', val.toString());
}

async function fetchPaidBalanceFromBackend() {
    try {
        const res = await fetch('/v1/user/balance?t=' + new Date().getTime());
        if (res.ok) {
            const data = await res.json();
            if (data && typeof data.paid_balance === 'number') {
                localStorage.setItem('aip_paid_balance', data.paid_balance.toString());
                return data.paid_balance;
            }
        }
    } catch(err) {
        console.error("Failed to fetch balance from backend:", err);
    }
    return parseInt(localStorage.getItem('aip_paid_balance') || '0');
}

async function rechargePaidBalanceOnBackend(addCredits, amountStr, packageName, projectName) {
    try {
        const res = await fetch('/v1/user/recharge', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                credits: addCredits,
                amount: amountStr,
                package: packageName,
                project: projectName || 'default'
            })
        });
        if (res.ok) {
            const data = await res.json();
            if (data && typeof data.paid_balance === 'number') {
                localStorage.setItem('aip_paid_balance', data.paid_balance.toString());
                return data.paid_balance;
            }
        }
    } catch(err) {
        console.error("Failed to recharge on backend:", err);
    }
    const localNew = parseInt(localStorage.getItem('aip_paid_balance') || '0') + addCredits;
    localStorage.setItem('aip_paid_balance', localNew.toString());
    return localNew;
}

function setActiveProjectName(name) {
    localStorage.setItem('aip_active_project', name);
    const label = document.getElementById('current-project-label');
    if (label) label.innerText = name;
}

async function initMasterTopbar() {
    const lang = getAppLanguage();
    const langText = document.getElementById('current-lang-text');
    if (langText) {
        langText.innerText = (AIP_I18N[lang] || AIP_I18N.en).language;
    }
    applyCommonTranslations();

    const projects = await getProjects();
    const activeName = getActiveProjectName();
    const label = document.getElementById('current-project-label');
    if (label) label.innerText = activeName;
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        initMasterTopbar();
    }, { once: true });
} else {
    initMasterTopbar();
}

function openSelectProjectModal() {
    renderProjectsModalTable();
    const modal = document.getElementById('select-project-modal');
    if (modal) modal.classList.add('active');
}

function closeSelectProjectModal() {
    const modal = document.getElementById('select-project-modal');
    if (modal) modal.classList.remove('active');
}

async function renderProjectsModalTable() {
    const projects = await getProjects();
    const activeName = getActiveProjectName();
    const tbody = document.getElementById('projects-modal-tbody');
    if (!tbody) return;
    tbody.innerHTML = '';

    projects.forEach(p => {
        const dateStr = p.created_at ? p.created_at.substring(0, 10) : '2026-08-16';
        const typeStr = p.type || 'prepaid';
        const isActive = p.project_name === activeName;

        const tr = document.createElement('tr');
        tr.className = `proj-row-selectable ${isActive ? 'active-proj' : ''}`;
        tr.style.cursor = 'pointer';
        tr.innerHTML = `
            <td style="padding: 12px 16px;">${dateStr}</td>
            <td style="padding: 12px 16px;"><strong>${p.project_name}</strong></td>
            <td style="padding: 12px 16px;"><strong>${typeStr}</strong></td>
        `;
        tr.onclick = () => {
            setActiveProjectName(p.project_name);
            closeSelectProjectModal();
            showToast(`Active project changed to: "${p.project_name}"`, 'success');
        };
        tbody.appendChild(tr);
    });

    const countLbl = document.getElementById('proj-count-label');
    if (countLbl) countLbl.innerText = `1-${projects.length} of ${projects.length}`;
}

function filterProjectsList() {
    const input = document.getElementById('project-search-input');
    if (!input) return;
    const query = input.value.toLowerCase();
    const rows = document.querySelectorAll('#projects-modal-tbody tr');
    rows.forEach(r => {
        const text = r.innerText.toLowerCase();
        r.style.display = text.includes(query) ? '' : 'none';
    });
}

function openCreatePrepaidProjectModal() {
    closeSelectProjectModal();
    const modal = document.getElementById('create-project-modal');
    if (modal) modal.classList.add('active');
}

function closeCreatePrepaidProjectModal() {
    const modal = document.getElementById('create-project-modal');
    if (modal) modal.classList.remove('active');
}

async function submitCreatePrepaidProject() {
    const input = document.getElementById('input-new-project-name');
    const name = (input && input.value.trim()) || 'New Prepaid Project';
    const select = document.getElementById('input-new-project-type');
    const type = (select && select.value) || 'prepaid';

    try {
        await fetch('/v1/user/projects', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ project_name: name, billing_type: type })
        });
    } catch (err) {}

    const projects = await getProjects();
    projects.push({ project_name: name, type: type, created_at: new Date().toISOString() });
    localStorage.setItem('aip_projects', JSON.stringify(projects));

    setActiveProjectName(name);
    closeCreatePrepaidProjectModal();
    showToast(`Prepaid Project "${name}" created successfully!`, 'success');
}

function staffShowToast(msg, type = 'info') {
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        document.body.appendChild(container);
    }
    container.style.cssText = 'position:fixed; top:6px; right:6px; z-index:10000; display:flex; flex-direction:column; align-items:flex-end; gap:6px; pointer-events:none; width:calc(100vw - 12px);';
    const toast = document.createElement('div');
    toast.className = `toast-msg toast-${type}`;
    toast.style.cssText = 'width:min(720px, calc(100vw - 24px)); min-height:38px; padding:7px 11px; border-radius:4px; display:flex; align-items:center; justify-content:space-between; gap:8px; color:#fff; font-size:12px; font-weight:600; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; box-shadow:0 4px 12px rgba(0,0,0,0.16); opacity:0.96; pointer-events:auto;';
    let bg = '#007bff';
    if (type === 'success') bg = '#10b981';
    if (type === 'warning') bg = '#f59e0b';
    if (type === 'error') bg = '#ef4444';

    toast.style.background = bg;
    toast.innerHTML = `<span style="overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${msg}</span><i class="fa-solid fa-xmark" style="cursor:pointer; flex:0 0 auto;" onclick="this.parentElement.remove()"></i>`;
    container.appendChild(toast);
    setTimeout(() => { toast.remove(); }, 3500);
}

function toggleStaffSidebar() {
    document.body.classList.toggle('aip-sidebar-collapsed');
    localStorage.setItem('aip_sidebar_collapsed', document.body.classList.contains('aip-sidebar-collapsed') ? '1' : '0');
}

function initStaffChrome() {
    if (!document.getElementById('aip-staff-chrome-style')) {
        const style = document.createElement('style');
        style.id = 'aip-staff-chrome-style';
        style.textContent = `
            #toast-container { position: fixed !important; top: 6px !important; right: 6px !important; z-index: 10000 !important; width: calc(100vw - 12px) !important; align-items: flex-end !important; gap: 6px !important; }
            #toast-container .toast-msg { width: min(720px, calc(100vw - 24px)) !important; min-width: 0 !important; max-width: none !important; min-height: 38px !important; padding: 7px 11px !important; border-radius: 4px !important; white-space: nowrap !important; overflow: hidden !important; }
            .aip-sidebar-collapsed .sidebar { display: none !important; }
            .layout-body, .main-content { min-width: 0 !important; }
            .main-content { overflow-x: hidden !important; }
            .chart-grid { grid-template-columns: repeat(3, minmax(0, 1fr)) !important; min-width: 0 !important; }
            .chart-card, .table-card { min-width: 0 !important; max-width: 100% !important; }
            .chart-card canvas { display: block; max-width: 100% !important; }
            .table-card { overflow-x: auto !important; }
            .table-card table { max-width: 100%; }
            .aip-sidebar-toggle { width: 30px; height: 30px; display: inline-flex; align-items: center; justify-content: center; border: 0; border-radius: 4px; background: rgba(255,255,255,0.14); color: #fff; cursor: pointer; font-size: 15px; }
            .aip-sidebar-toggle:hover { background: rgba(255,255,255,0.25); }
            @media (max-width: 700px) { .aip-sidebar-toggle { display: inline-flex; } }
        `;
        document.head.appendChild(style);
    }

    const headerLeft = document.querySelector('.top-header .header-left');
    if (headerLeft && !document.getElementById('aip-sidebar-toggle')) {
        const toggle = document.createElement('button');
        toggle.id = 'aip-sidebar-toggle';
        toggle.className = 'aip-sidebar-toggle';
        toggle.type = 'button';
        toggle.title = 'Toggle sidebar';
        toggle.setAttribute('aria-label', 'Toggle sidebar');
        toggle.innerHTML = '<i class="fa-solid fa-bars"></i>';
        toggle.addEventListener('click', toggleStaffSidebar);
        headerLeft.insertBefore(toggle, headerLeft.firstChild);
    }

    if (localStorage.getItem('aip_sidebar_collapsed') === '1') {
        document.body.classList.add('aip-sidebar-collapsed');
    }

    // Page scripts may define their own showToast; replace it with the shared renderer.
    window.showToast = staffShowToast;
}

function initMasterSidebar() {
    const sidebar = document.querySelector('.sidebar');
    if (!sidebar) return;

    const path = window.location.pathname;

    sidebar.innerHTML = `
        <div class="nav-section">
            <div class="section-title" onclick="toggleNavSection(this)" style="cursor:pointer; display:flex; align-items:center; justify-content:space-between; color:#64748b;">
                <span><i class="fa-solid fa-terminal" style="margin-right: 8px; width: 14px;"></i> Console</span>
                <i class="fa-solid fa-chevron-down toggle-icon" style="font-size: 10px; transition: transform 0.2s;"></i>
            </div>
            <ul class="nav-list">
                <li class="nav-item ${path === '/staff/dashboard' || path === '/staff' ? 'active' : ''}"><a href="/staff/dashboard"><i class="fa-solid fa-chart-pie" style="width: 16px; text-align: center;"></i> Dashboard</a></li>
                <li class="nav-item ${path === '/staff/apis' ? 'active' : ''}"><a href="/staff/apis"><i class="fa-solid fa-cubes" style="width: 16px; text-align: center;"></i> APIs</a></li>
                <li class="nav-item ${path === '/staff/keys' ? 'active' : ''}"><a href="/staff/keys"><i class="fa-solid fa-key" style="width: 16px; text-align: center;"></i> API Keys</a></li>
                <li class="nav-item ${path === '/staff/report' ? 'active' : ''}"><a href="/staff/report"><i class="fa-solid fa-chart-line" style="width: 16px; text-align: center;"></i> API report</a></li>
            </ul>
        </div>

        <div class="nav-section">
            <div class="section-title" ${path === '/staff/payment' ? 'style="border-left: 3px solid var(--fpt-cyan);"' : ''}>
                <a href="/staff/payment" style="color:#64748b; text-decoration:none; display:flex; align-items:center; gap:8px; font-size:12.5px; font-weight:700; text-transform:uppercase;">
                    <i class="fa-solid fa-credit-card" style="width: 14px;"></i> Payment history
                </a>
            </div>
        </div>
        <div class="nav-section">
            <div class="section-title" ${path === '/staff/contact' ? 'style="border-left: 3px solid var(--fpt-cyan);"' : ''}>
                <a href="/staff/contact" style="color:#64748b; text-decoration:none; display:flex; align-items:center; gap:8px; font-size:12.5px; font-weight:700; text-transform:uppercase;">
                    <i class="fa-solid fa-headset" style="width: 14px;"></i> Contact us
                </a>
            </div>
        </div>
    `;
}

function toggleNavSection(headerEl) {
    const navList = headerEl.nextElementSibling;
    const icon = headerEl.querySelector('.toggle-icon');
    if (navList) {
        if (navList.style.display === 'none') {
            navList.style.display = 'block';
            if (icon) icon.style.transform = 'rotate(0deg)';
        } else {
            navList.style.display = 'none';
            if (icon) icon.style.transform = 'rotate(-90deg)';
        }
    }
}

document.addEventListener('DOMContentLoaded', function() {
    initStaffChrome();
    initMasterSidebar();
});
