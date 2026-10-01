/**
 * staff_layout.js - Shared Unified Layout & Modal Component for AIP Staff Portal
 * Ensures 100% identical Topbar, Sidebar, and Modals across all Staff pages.
 */

(function () {
    'use strict';

    // 1. Shared CSS Styles for Topbar, Sidebar, and Atlas Modals
    const SHARED_CSS = `
        :root {
            --font-heading: 'Outfit', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            --font-body: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            --font-code: 'Fira Code', monospace;
            --aip-blue: #0f4c81;
            --bg-page: #f8fafc;
            --sidebar-bg: #ffffff;
            --text-dark: #001e2b;
            --text-sub: #5c6c75;
            --border-color: #e8edeb;
            --primary: #00684a;
            --primary-hover: #025039;
        }

        /* Top Header */
        .top-header {
            background: #0f4c81 !important;
            height: 50px !important;
            padding: 0 24px !important;
            display: flex !important;
            align-items: center !important;
            justify-content: space-between !important;
            color: #fff !important;
            font-size: 13px !important;
            position: sticky !important;
            top: 0 !important;
            z-index: 1000 !important;
            font-family: var(--font-body);
        }
        .header-left { display: flex; align-items: center; gap: 20px; }
        .brand-logo {
            font-family: var(--font-heading);
            font-size: 17px;
            font-weight: 800;
            color: #fff !important;
            text-decoration: none;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .project-selector {
            background: rgba(255, 255, 255, 0.15);
            border-radius: 4px;
            padding: 5px 12px;
            font-size: 12px;
            font-weight: 500;
            cursor: pointer;
            display: flex;
            align-items: center;
            gap: 8px;
            color: #fff;
            transition: background 0.15s ease;
        }
        .project-selector:hover { background: rgba(255, 255, 255, 0.25); }

        .header-right { display: flex; align-items: center; gap: 20px; }
        .user-menu { display: flex; align-items: center; gap: 8px; font-weight: 600; }

        html {
            overflow-y: scroll !important;
        }
        .layout-body {
            display: flex !important;
            flex: 1 !important;
            min-height: calc(100vh - 50px) !important;
        }

        /* Sidebar Standard */
        .sidebar {
            width: 220px !important;
            min-width: 220px !important;
            max-width: 220px !important;
            background: #ffffff !important;
            border-right: 1px solid #e8edeb !important;
            padding: 16px 0 !important;
            position: sticky !important;
            top: 50px !important;
            height: calc(100vh - 50px) !important;
            max-height: calc(100vh - 50px) !important;
            align-self: flex-start !important;
            overflow-y: auto !important;
            flex-shrink: 0 !important;
            box-sizing: border-box !important;
            font-family: var(--font-body);
        }
        .main-content {
            flex: 1 !important;
            min-width: 0 !important;
        }
        .nav-section { margin-bottom: 14px; }
        .section-title {
            font-size: 11px !important;
            font-weight: 700 !important;
            text-transform: uppercase !important;
            color: #5c6c75 !important;
            padding: 8px 18px !important;
            letter-spacing: 0.05em !important;
            display: flex !important;
            align-items: center !important;
            justify-content: space-between !important;
            cursor: pointer !important;
            user-select: none !important;
        }
        .section-title span { display: flex; align-items: center; gap: 8px; }
        .section-title .toggle-icon { font-size: 10px; transition: transform 0.2s; color: #64748b; }
        .nav-list { list-style: none; margin: 0; padding: 0; }
        .nav-item a {
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 8px 18px;
            font-size: 13px;
            font-weight: 500;
            color: #334155;
            text-decoration: none;
            transition: all 0.12s ease;
            border-left: 4px solid transparent;
        }
        .nav-item a i {
            color: #64748b;
            font-size: 13px;
            width: 16px;
            text-align: center;
        }
        .nav-item.active a,
        .nav-item a:hover {
            background: #f0f4f8 !important;
            color: #001e2b !important;
            border-left-color: #0f4c81 !important;
            font-weight: 700 !important;
        }
        .nav-item.active a i,
        .nav-item a:hover i {
            color: #001e2b !important;
        }

        /* Direct links: PAYMENT HISTORY & CONTACT US */
        .nav-direct-link a {
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 9px 18px;
            font-size: 11.5px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.04em;
            color: #5c6c75;
            text-decoration: none;
            transition: all 0.12s ease;
            border-left: 4px solid transparent;
        }
        .nav-direct-link a i {
            color: #5c6c75;
            font-size: 13px;
            width: 16px;
            text-align: center;
        }
        .nav-direct-link.active a,
        .nav-direct-link a:hover {
            background: #f0f4f8 !important;
            color: #001e2b !important;
            border-left-color: #0f4c81 !important;
            font-weight: 700 !important;
        }
        .nav-direct-link.active a i,
        .nav-direct-link a:hover i {
            color: #001e2b !important;
        }

        /* Shared Atlas Project Modal Overlay */
        .modal-overlay {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(15, 23, 42, 0.45);
            z-index: 99999;
            align-items: center;
            justify-content: center;
            backdrop-filter: blur(3px);
        }
        .modal-overlay.active { display: flex !important; }

        .atlas-modal-box {
            background: #ffffff;
            width: 620px;
            border-radius: 12px;
            border: 1px solid #e8edeb;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.18);
            overflow: hidden;
            font-family: var(--font-body);
            animation: modalFadeIn 0.15s ease-out;
        }
        @keyframes modalFadeIn {
            from { opacity: 0; transform: translateY(-8px) scale(0.98); }
            to { opacity: 1; transform: translateY(0) scale(1); }
        }

        .atlas-modal-header {
            background: #ffffff;
            color: #001e2b;
            font-size: 16.5px;
            font-weight: 700;
            padding: 18px 24px;
            border-bottom: 1px solid #e8edeb;
            font-family: var(--font-heading);
        }
        .atlas-modal-body {
            padding: 22px 24px;
        }
        .atlas-modal-footer {
            border-top: 1px solid #f1f5f9;
            padding: 14px 24px;
            display: flex;
            align-items: center;
            justify-content: flex-end;
            gap: 10px;
            background: #ffffff;
        }

        .btn-atlas-modal-cancel {
            background: #f8fafc;
            border: 1px solid #cbd5e1;
            border-radius: 6px;
            padding: 7px 18px;
            font-weight: 700;
            font-size: 12px;
            color: #334155;
            cursor: pointer;
            transition: all 0.15s ease;
        }
        .btn-atlas-modal-cancel:hover {
            background: #e2e8f0;
            color: #0f172a;
        }

        .btn-atlas-modal-primary {
            background: #00684a;
            color: #ffffff;
            border: 1px solid #00684a;
            border-radius: 6px;
            font-weight: 700;
            font-size: 12px;
            padding: 7px 18px;
            cursor: pointer;
            display: inline-flex;
            align-items: center;
            gap: 6px;
            transition: all 0.15s ease;
        }
        .btn-atlas-modal-primary:hover {
            background: #025039;
            border-color: #025039;
        }

        .proj-table-wrap {
            border: 1px solid #e8edeb;
            border-radius: 8px;
            overflow: hidden;
            margin-bottom: 16px;
        }
        .proj-table {
            width: 100%;
            border-collapse: collapse;
            text-align: left;
            font-size: 12.5px;
        }
        .proj-table th {
            padding: 12px 18px;
            color: #5c6c75;
            font-weight: 600;
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.04em;
            background: #f9fbfa;
            border-bottom: 1px solid #e8edeb;
        }
        .proj-table td {
            padding: 12px 18px;
            border-bottom: 1px solid #f4f6f5;
            color: #001e2b;
        }
        .proj-row-selectable {
            cursor: pointer;
            transition: background 0.12s ease;
        }
        .proj-row-selectable:hover {
            background: #f4f6f5 !important;
        }
        .proj-row-selectable.active-proj {
            background: rgba(0, 104, 74, 0.06) !important;
        }

        /* Toast Container */
        #toast-container { position: fixed; top: 24px; right: 24px; z-index: 100000; display: flex; flex-direction: column; gap: 10px; }
    `;

    // 2. Inject CSS
    function injectSharedStyles() {
        if (document.getElementById('staff-shared-layout-css')) return;
        const style = document.createElement('style');
        style.id = 'staff-shared-layout-css';
        style.innerHTML = SHARED_CSS;
        document.head.appendChild(style);
    }

    // 3. Project Storage State - Connected to MongoDB Atlas
    async function getProjects() {
        try {
            const res = await fetch('/v1/user/projects');
            if (res.ok) {
                const data = await res.json();
                if (Array.isArray(data)) {
                    localStorage.setItem('aip_projects', JSON.stringify(data));
                    return data;
                }
            }
        } catch (err) {
            console.warn('Cannot fetch projects from MongoDB:', err);
        }

        const raw = localStorage.getItem('aip_projects');
        if (raw) {
            try { return JSON.parse(raw); } catch (e) {}
        }
        return [];
    }

    function setProjects(list) {
        localStorage.setItem('aip_projects', JSON.stringify(list));
    }

    function getActiveProjectName() {
        const active = localStorage.getItem('aip_active_project');
        if (active) return active;
        const raw = localStorage.getItem('aip_projects');
        if (raw) {
            try {
                const list = JSON.parse(raw);
                if (list.length > 0 && list[0].project_name) return list[0].project_name;
            } catch (e) {}
        }
        return 'Default Project';
    }

    function setActiveProjectName(name) {
        localStorage.setItem('aip_active_project', name);
        const topLabel = document.getElementById('current-project-label');
        if (topLabel) topLabel.innerText = name;
        const breadcrumbLabel = document.getElementById('breadcrumb-project-name');
        if (breadcrumbLabel) breadcrumbLabel.innerText = name;
    }

    // 4. Modal Render & Open/Close Handlers
    function ensureModalsInDOM() {
        // Remove duplicate or conflicting old modals
        const oldSelect = document.getElementById('select-project-modal');
        if (oldSelect) oldSelect.remove();
        const oldCreate = document.getElementById('create-project-modal');
        if (oldCreate) oldCreate.remove();

        const modalContainer = document.createElement('div');
        modalContainer.id = 'staff-unified-modals';
        modalContainer.innerHTML = `
            <!-- SELECT A PROJECT MODAL (Exact Replica of User Screenshot 1) -->
            <div class="modal-overlay" id="select-project-modal" onclick="if(event.target===this) StaffLayout.closeSelectProjectModal()">
                <div class="atlas-modal-box">
                    <div class="atlas-modal-header">Select a project</div>
                    <div class="atlas-modal-body">
                        <div style="display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 20px;">
                            <div style="position: relative; flex: 1;">
                                <input type="text" id="project-search-input" onkeyup="StaffLayout.filterProjectsList()" placeholder="Search" style="width: 100%; border: none; border-bottom: 1.5px solid #cbd5e1; padding: 8px 32px 8px 0; font-size: 13.5px; outline: none; font-family: var(--font-body); color: #001e2b; background: transparent;">
                                <i class="fa-solid fa-magnifying-glass" style="position: absolute; right: 8px; top: 10px; color: #64748b; font-size: 14px;"></i>
                            </div>
                            <button class="btn-atlas-modal-primary" onclick="StaffLayout.openCreatePrepaidProjectModal()"><i class="fa-solid fa-plus"></i> CREATE PREPAID PROJECT</button>
                        </div>

                        <div class="proj-table-wrap">
                            <table class="proj-table">
                                <thead>
                                    <tr>
                                        <th>Created time ↓</th>
                                        <th>Name</th>
                                        <th>Type</th>
                                    </tr>
                                </thead>
                                <tbody id="projects-modal-tbody"></tbody>
                            </table>
                        </div>

                        <div style="display: flex; align-items: center; justify-content: flex-end; gap: 16px; font-size: 12px; color: #64748b;">
                            <span>Rows per page</span>
                            <select style="border: 1px solid #cbd5e1; border-radius: 4px; padding: 3px 8px; font-size: 12px; outline: none; background: #fff;"><option>5</option></select>
                            <span id="proj-count-label">1-2 of 2</span>
                            <i class="fa-solid fa-chevron-left" style="cursor: pointer;"></i>
                            <i class="fa-solid fa-chevron-right" style="cursor: pointer;"></i>
                        </div>
                    </div>
                    <div class="atlas-modal-footer">
                        <button class="btn-atlas-modal-cancel" onclick="StaffLayout.closeSelectProjectModal()">CLOSE</button>
                    </div>
                </div>
            </div>

            <!-- CREATE PREPAID PROJECT MODAL -->
            <div class="modal-overlay" id="create-project-modal" onclick="if(event.target===this) StaffLayout.closeCreatePrepaidProjectModal()">
                <div class="atlas-modal-box" style="width: 460px;">
                    <div class="atlas-modal-header">Create Prepaid Project</div>
                    <div class="atlas-modal-body">
                        <div style="margin-bottom: 16px;">
                            <label style="font-size: 12px; font-weight: 600; color: #5c6c75; display: block; margin-bottom: 4px;">Project Name</label>
                            <input type="text" id="input-new-project-name" placeholder="Ví dụ: Dự án AI Doanh Nghiệp" value="" style="width: 100%; border: none; border-bottom: 1.5px solid #cbd5e1; padding: 8px 0; font-size: 13.5px; outline: none; color: #001e2b;">
                        </div>
                        <div>
                            <label style="font-size: 12px; font-weight: 600; color: #5c6c75; display: block; margin-bottom: 4px;">Billing Type</label>
                            <select id="input-new-project-type" style="width: 100%; border: none; border-bottom: 1.5px solid #cbd5e1; padding: 8px 0; font-size: 13.5px; outline: none; color: #001e2b; background: transparent;">
                                <option value="prepaid">Prepaid (Quota deduction)</option>
                                <option value="postpaid">Postpaid (Monthly invoice)</option>
                            </select>
                        </div>
                    </div>
                    <div class="atlas-modal-footer">
                        <button class="btn-atlas-modal-cancel" onclick="StaffLayout.closeCreatePrepaidProjectModal()">CANCEL</button>
                        <button class="btn-atlas-modal-primary" onclick="StaffLayout.submitCreatePrepaidProject()"><i class="fa-solid fa-plus"></i> CREATE</button>
                    </div>
                </div>
            </div>
        `;
        document.body.appendChild(modalContainer);
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
        const tbody = document.getElementById('projects-modal-tbody');
        if (!tbody) return;
        tbody.innerHTML = `<tr><td colspan="3" style="text-align:center; padding: 20px; color: #64748b;"><i class="fa-solid fa-spinner fa-spin" style="margin-right:8px;"></i> Đang tải danh sách dự án từ MongoDB...</td></tr>`;

        const projects = await getProjects();
        const activeName = getActiveProjectName();
        tbody.innerHTML = '';

        if (!projects || projects.length === 0) {
            tbody.innerHTML = `<tr><td colspan="3" style="text-align:center; padding: 24px; color: #64748b;">Chưa có dự án nào trong cơ sở dữ liệu MongoDB. Nhấn "+ CREATE PREPAID PROJECT" để tạo dự án mới.</td></tr>`;
            const countLabel = document.getElementById('proj-count-label');
            if (countLabel) countLabel.innerText = `0 of 0`;
            return;
        }

        projects.forEach(p => {
            const dateStr = p.created_at ? (p.created_at.includes('T') ? p.created_at.split('T')[0] : p.created_at.substring(0, 10)) : '—';
            const typeStr = p.type || 'prepaid';
            const isActive = p.project_name === activeName;

            const tr = document.createElement('tr');
            tr.className = `proj-row-selectable ${isActive ? 'active-proj' : ''}`;
            tr.innerHTML = `
                <td style="padding: 12px 18px; color: #334155;">${dateStr}</td>
                <td style="padding: 12px 18px; color: #001e2b; font-weight: 700;">${p.project_name}</td>
                <td style="padding: 12px 18px; color: #001e2b; font-weight: 700; text-transform: uppercase;">${typeStr}</td>
            `;
            tr.onclick = () => {
                setActiveProjectName(p.project_name);
                closeSelectProjectModal();
                showToast(`Đã chọn dự án: "${p.project_name}"`, 'success');
                window.dispatchEvent(new CustomEvent('aip-project-changed', { detail: p }));
            };
            tbody.appendChild(tr);
        });

        const countLabel = document.getElementById('proj-count-label');
        if (countLabel) countLabel.innerText = `1-${projects.length} of ${projects.length}`;
    }

    function filterProjectsList() {
        const query = (document.getElementById('project-search-input')?.value || '').toLowerCase();
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
        const nameInput = document.getElementById('input-new-project-name');
        const typeInput = document.getElementById('input-new-project-type');
        const name = nameInput?.value.trim() || 'New Prepaid Project';
        const type = typeInput?.value || 'prepaid';

        try {
            const res = await fetch('/v1/user/projects', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    project_name: name,
                    billing_type: type
                })
            });

            if (!res.ok) {
                const errData = await res.json().catch(() => ({}));
                showToast(errData.detail || 'Không thể tạo dự án trong cơ sở dữ liệu MongoDB.', 'error');
                return;
            }

            const data = await res.json();
            const saved = data.project || { project_name: name, type: type, created_at: new Date().toISOString() };

            // Re-fetch clean data from MongoDB
            await getProjects();
            setActiveProjectName(saved.project_name || name);
            closeCreatePrepaidProjectModal();
            showToast(`Dự án "${name}" đã được lưu thành công vào MongoDB!`, 'success');
            window.dispatchEvent(new CustomEvent('aip-project-changed', { detail: saved }));
        } catch (err) {
            console.error('Error creating project in database:', err);
            showToast('Lỗi kết nối máy chủ khi tạo dự án vào MongoDB.', 'error');
        }
    }

    // 5. Toast Notification System
    function showToast(msg, type = 'info') {
        let container = document.getElementById('toast-container');
        if (!container) {
            container = document.createElement('div');
            container.id = 'toast-container';
            document.body.appendChild(container);
        }
        const toast = document.createElement('div');
        toast.style.cssText = 'min-width:280px; padding:12px 18px; border-radius:8px; color:#fff; font-size:13px; font-weight:600; display:flex; align-items:center; justify-content:space-between; gap:10px; box-shadow:0 10px 25px rgba(0,0,0,0.2); opacity:0.96; font-family:var(--font-body); z-index:100000;';
        toast.style.background = type === 'success' ? '#10b981' : (type === 'error' ? '#ef4444' : (type === 'warning' ? '#f59e0b' : '#00a4b8'));
        toast.innerHTML = `<span>${msg}</span><span style="cursor:pointer; margin-left:auto; font-size:16px;" onclick="this.parentElement.remove()">&times;</span>`;
        container.appendChild(toast);
        setTimeout(() => { toast.remove(); }, 3500);
    }

    // 6. Navigation Toggle
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

    // 7. Language Switcher
    function toggleLangDropdown(e) {
        if (e) e.stopPropagation();
        const menu = document.getElementById('lang-dropdown-menu');
        if (menu) menu.style.display = (menu.style.display === 'none' || !menu.style.display) ? 'block' : 'none';
    }

    function setAppLanguage(lang) {
        localStorage.setItem('aip_lang', lang);
        const textEl = document.getElementById('current-lang-text');
        if (textEl) textEl.innerText = lang === 'vi' ? 'Tiếng Việt' : 'English';
        const menu = document.getElementById('lang-dropdown-menu');
        if (menu) menu.style.display = 'none';
        showToast(lang === 'vi' ? 'Đã chuyển ngôn ngữ sang Tiếng Việt' : 'Switched language to English', 'info');
    }

    // 8. Authentication
    function checkMandatoryAuth() {
        const userSession = localStorage.getItem('aip_user_session') || sessionStorage.getItem('aip_user_session');
        const headerUsername = document.getElementById('header-username');
        if (userSession) {
            try {
                const user = JSON.parse(userSession);
                if (headerUsername) headerUsername.innerText = user.full_name || 'Nam Lê';
            } catch (e) {}
        } else {
            if (headerUsername) headerUsername.innerText = 'Nam Lê';
        }
    }

    function logoutUser() {
        localStorage.removeItem('aip_user_session');
        sessionStorage.removeItem('aip_user_session');
        window.location.href = '/login';
    }

    // 9. Standard Topbar & Sidebar Markup
    function syncTopbarAndSidebar() {
        const path = window.location.pathname.toLowerCase();

        // 1. Update Project Label
        const activeProject = getActiveProjectName();
        const projLabel = document.getElementById('current-project-label');
        if (projLabel) projLabel.innerText = activeProject;
        const breadcrumbProject = document.getElementById('breadcrumb-project-name');
        if (breadcrumbProject) breadcrumbProject.innerText = activeProject;

        // 2. Synchronize active state in sidebar exactly like Image 2
        document.querySelectorAll('.sidebar .nav-item').forEach(item => {
            const link = item.querySelector('a');
            if (link && link.getAttribute('href') && path.endsWith(link.getAttribute('href').toLowerCase())) {
                item.classList.add('active');
            } else {
                item.classList.remove('active');
            }
        });

        document.querySelectorAll('.sidebar .nav-direct-link').forEach(item => {
            const link = item.querySelector('a');
            if (link && link.getAttribute('href') && path.endsWith(link.getAttribute('href').toLowerCase())) {
                item.classList.add('active');
            } else {
                item.classList.remove('active');
            }
        });

        // Close dropdown when clicked outside
        document.addEventListener('click', (e) => {
            const menu = document.getElementById('lang-dropdown-menu');
            if (menu && !e.target.closest('#lang-dropdown-menu') && !e.target.closest('.header-right')) {
                menu.style.display = 'none';
            }
        });
    }

    // Public API under window.StaffLayout & window globals
    const StaffLayout = {
        openSelectProjectModal,
        closeSelectProjectModal,
        openCreatePrepaidProjectModal,
        closeCreatePrepaidProjectModal,
        submitCreatePrepaidProject,
        renderProjectsModalTable,
        filterProjectsList,
        getProjects,
        setProjects,
        getActiveProjectName,
        setActiveProjectName,
        showToast,
        toggleNavSection,
        toggleLangDropdown,
        setAppLanguage,
        checkMandatoryAuth,
        logoutUser,
        init() {
            injectSharedStyles();
            ensureModalsInDOM();
            syncTopbarAndSidebar();
            checkMandatoryAuth();
        }
    };

    window.StaffLayout = StaffLayout;

    // Backward-compatible global bindings
    window.openSelectProjectModal = openSelectProjectModal;
    window.closeSelectProjectModal = closeSelectProjectModal;
    window.openCreatePrepaidProjectModal = openCreatePrepaidProjectModal;
    window.closeCreatePrepaidProjectModal = closeCreatePrepaidProjectModal;
    window.submitCreatePrepaidProject = submitCreatePrepaidProject;
    window.renderProjectsModalTable = renderProjectsModalTable;
    window.filterProjectsList = filterProjectsList;
    window.getProjects = getProjects;
    window.setProjects = setProjects;
    window.getActiveProjectName = getActiveProjectName;
    window.setActiveProjectName = setActiveProjectName;
    window.showToast = showToast;
    window.toggleNavSection = toggleNavSection;
    window.toggleLangDropdown = toggleLangDropdown;
    window.setAppLanguage = setAppLanguage;
    window.checkMandatoryAuth = checkMandatoryAuth;
    window.logoutUser = logoutUser;

    // Auto-init on DOMContentLoaded
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', StaffLayout.init);
    } else {
        StaffLayout.init();
    }
})();
