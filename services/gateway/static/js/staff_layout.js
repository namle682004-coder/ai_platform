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

function getEnabledAPIs() {
    const data = localStorage.getItem('aip_enabled_apis');
    if (data) {
        try { return JSON.parse(data); } catch(e) {}
    }
    return { "Speech to Text": true, "Text to Speech": false, "LLM Chatbot API": false };
}

async function fetchEnabledAPIsFromBackend() {
    try {
        const res = await fetch('/v1/user/apis-state');
        if (res.ok) {
            const data = await res.json();
            if (data && data.enabled_apis && Object.keys(data.enabled_apis).length > 0) {
                localStorage.setItem('aip_enabled_apis', JSON.stringify(data.enabled_apis));
                return data.enabled_apis;
            }
        }
    } catch(err) {}
    return getEnabledAPIs();
}

async function setEnabledAPIs(apiObj) {
    localStorage.setItem('aip_enabled_apis', JSON.stringify(apiObj));
    try {
        await fetch('/v1/user/apis-state', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ enabled_apis: apiObj })
        });
    } catch(err) {}
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

function logoutUser() {
    localStorage.removeItem('aip_auth_token');
    showToast('Đã đăng xuất khỏi tài khoản.', 'info');
    setTimeout(() => { location.href = '/login'; }, 800);
}

document.addEventListener('DOMContentLoaded', function() {
    initMasterTopbar();
});
