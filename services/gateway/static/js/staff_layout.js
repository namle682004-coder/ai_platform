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
        search: "Search"
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
        search: "Tìm kiếm"
    }
};

function getAppLanguage() {
    return localStorage.getItem('aip_lang') || 'en';
}

function setAppLanguage(lang) {
    localStorage.setItem('aip_lang', lang);
    location.reload();
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
        langText.innerText = lang === 'vi' ? 'Tiếng Việt' : 'English';
    }

    const projects = await getProjects();
    const activeName = getActiveProjectName();
    const label = document.getElementById('current-project-label');
    if (label) label.innerText = activeName;
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

function showToast(msg, type = 'info') {
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        document.body.appendChild(container);
    }
    const toast = document.createElement('div');
    toast.className = `toast-msg toast-${type}`;
    let bg = '#007bff';
    if (type === 'success') bg = '#10b981';
    if (type === 'warning') bg = '#f59e0b';
    if (type === 'error') bg = '#ef4444';

    toast.style.background = bg;
    toast.innerHTML = `<span>${msg}</span><i class="fa-solid fa-xmark" style="cursor:pointer;" onclick="this.parentElement.remove()"></i>`;
    container.appendChild(toast);
    setTimeout(() => { toast.remove(); }, 3500);
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
            <div class="section-title" onclick="toggleNavSection(this)" style="cursor:pointer; display:flex; align-items:center; justify-content:space-between; color:#64748b;">
                <span><i class="fa-solid fa-id-card" style="margin-right: 8px; width: 14px;"></i> OCR & Reader</span>
                <i class="fa-solid fa-chevron-down toggle-icon" style="font-size: 10px; transition: transform 0.2s;"></i>
            </div>
            <ul class="nav-list">
                <li class="nav-item ${path.includes('ocr-dl') ? 'active' : ''}"><a href="/staff/service-ocr-dl"><i class="fa-solid fa-id-card-clip" style="width: 16px; text-align: center;"></i> Driver's License</a></li>
                <li class="nav-item ${path.includes('ocr-id') ? 'active' : ''}"><a href="/staff/service-ocr-id"><i class="fa-solid fa-address-card" style="width: 16px; text-align: center;"></i> ID Recognition</a></li>
                <li class="nav-item ${path.includes('ocr-passport') ? 'active' : ''}"><a href="/staff/service-ocr-passport"><i class="fa-solid fa-passport" style="width: 16px; text-align: center;"></i> Passport Recog</a></li>
            </ul>
        </div>

        <div class="nav-section">
            <div class="section-title" onclick="toggleNavSection(this)" style="cursor:pointer; display:flex; align-items:center; justify-content:space-between; color:#64748b;">
                <span><i class="fa-solid fa-eye" style="margin-right: 8px; width: 14px;"></i> Speech & Vision</span>
                <i class="fa-solid fa-chevron-down toggle-icon" style="font-size: 10px; transition: transform 0.2s;"></i>
            </div>
            <ul class="nav-list">
                <li class="nav-item ${path.includes('service-stt') ? 'active' : ''}"><a href="/staff/service-stt"><i class="fa-solid fa-microphone-lines" style="width: 16px; text-align: center;"></i> Speech to Text</a></li>
                <li class="nav-item ${path.includes('service-tts') ? 'active' : ''}"><a href="/staff/service-tts"><i class="fa-solid fa-volume-high" style="width: 16px; text-align: center;"></i> Text to Speech</a></li>
                <li class="nav-item ${path.includes('vision-facematch') ? 'active' : ''}"><a href="/staff/service-vision-facematch"><i class="fa-solid fa-user-check" style="width: 16px; text-align: center;"></i> FaceMatch</a></li>
                <li class="nav-item ${path.includes('vision-liveness') ? 'active' : ''}"><a href="/staff/service-vision-liveness"><i class="fa-solid fa-user-shield" style="width: 16px; text-align: center;"></i> Liveness v3</a></li>
            </ul>
        </div>

        <div class="nav-section">
            <div class="section-title" onclick="toggleNavSection(this)" style="cursor:pointer; display:flex; align-items:center; justify-content:space-between; color:#64748b;">
                <span><i class="fa-solid fa-brain" style="margin-right: 8px; width: 14px;"></i> Generative AI</span>
                <i class="fa-solid fa-chevron-down toggle-icon" style="font-size: 10px; transition: transform 0.2s;"></i>
            </div>
            <ul class="nav-list">
                <li class="nav-item ${path.includes('service-llm') ? 'active' : ''}"><a href="/staff/service-llm"><i class="fa-solid fa-robot" style="width: 16px; text-align: center;"></i> LLM Chatbot</a></li>
                <li class="nav-item ${path.includes('service-image') ? 'active' : ''}"><a href="/staff/service-image"><i class="fa-solid fa-image" style="width: 16px; text-align: center;"></i> Image Gen API</a></li>
            </ul>
        </div>

        <div class="nav-section">
            <div class="section-title" onclick="toggleNavSection(this)" style="cursor:pointer; display:flex; align-items:center; justify-content:space-between; color:#64748b;">
                <span><i class="fa-solid fa-font" style="margin-right: 8px; width: 14px;"></i> Natural Language</span>
                <i class="fa-solid fa-chevron-down toggle-icon" style="font-size: 10px; transition: transform 0.2s;"></i>
            </div>
            <ul class="nav-list">
                <li class="nav-item ${path.includes('service-moderation') ? 'active' : ''}"><a href="/staff/service-moderation"><i class="fa-solid fa-shield-halved" style="width: 16px; text-align: center;"></i> Moderation API</a></li>
                <li class="nav-item ${path.includes('nlp-embeddings') ? 'active' : ''}"><a href="/staff/service-nlp-embeddings"><i class="fa-solid fa-magnifying-glass" style="width: 16px; text-align: center;"></i> Embedding API</a></li>
                <li class="nav-item ${path.includes('nlp-summarization') ? 'active' : ''}"><a href="/staff/service-nlp-summarization"><i class="fa-solid fa-file-lines" style="width: 16px; text-align: center;"></i> Summarize API</a></li>
                <li class="nav-item ${path.includes('nlp-translation') ? 'active' : ''}"><a href="/staff/service-nlp-translation"><i class="fa-solid fa-language" style="width: 16px; text-align: center;"></i> Translation API</a></li>
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
    initMasterTopbar();
    initMasterSidebar();
});
