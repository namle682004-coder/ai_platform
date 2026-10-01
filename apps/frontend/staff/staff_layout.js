import '/staff/applications_nav.js';

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
            min-height: 50px !important;
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
        .header-left { display: flex; align-items: center; gap: 14px; flex-shrink: 0; }
        .sidebar-toggle {
            width: 32px;
            height: 32px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            border: 1px solid rgba(255, 255, 255, 0.24);
            border-radius: 6px;
            background: rgba(255, 255, 255, 0.1);
            color: #ffffff;
            font-size: 14px;
            cursor: pointer;
            transition: background 0.15s ease, border-color 0.15s ease;
            flex-shrink: 0;
        }
        .sidebar-toggle:hover,
        .sidebar-toggle:focus-visible {
            background: rgba(255, 255, 255, 0.22);
            border-color: rgba(255, 255, 255, 0.42);
            outline: none;
        }
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
        body {
            font-size: 13px !important;
            line-height: 1.45 !important;
        }
        .layout-body {
            display: flex !important;
            flex: 1 !important;
            min-height: calc(100vh - 50px) !important;
        }
        .brand-logo i {
            color: #ffffff;
            font-size: 17px;
        }
        .project-selector i,
        .user-menu i {
            color: #ffffff;
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
            transition: width 0.2s ease, min-width 0.2s ease, max-width 0.2s ease, padding 0.2s ease, border-color 0.2s ease;
        }
        body.staff-sidebar-collapsed .sidebar {
            width: 0 !important;
            min-width: 0 !important;
            max-width: 0 !important;
            padding-left: 0 !important;
            padding-right: 0 !important;
            border-right-width: 0 !important;
            overflow: hidden !important;
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
        .app-category { list-style: none; }
        .app-category-toggle {
            width: calc(100% - 24px);
            min-height: 32px;
            margin: 3px 12px;
            padding: 5px 8px 5px 10px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 8px;
            border: 1px solid transparent;
            border-radius: 6px;
            background: transparent;
            color: #5c6c75;
            font: 600 11px/1.3 var(--font-body);
            text-align: left;
            cursor: pointer;
            transition: background 0.15s ease, color 0.15s ease;
        }
        .app-category-toggle:hover { background: #f4f6f5; color: #001e2b; }
        .app-category-toggle[aria-expanded="true"] {
            background: #eaf2f8;
            color: #0f4c81;
            font-weight: 700;
        }
        .app-category-label { min-width: 0; }
        .app-category-chevron {
            color: #8495a2;
            font-size: 9px;
            transition: transform 0.15s ease;
        }
        .app-category-toggle[aria-expanded="true"] .app-category-chevron {
            transform: rotate(180deg);
        }
        .app-category-items[hidden] { display: none; }
        .app-category-items .nav-item a {
            padding-left: 30px;
            font-size: 12px;
        }
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
        .staff-select {
            position: relative;
            display: inline-flex;
            width: var(--staff-select-width, auto);
            max-width: 100%;
            min-width: 0;
            vertical-align: middle;
        }
        .staff-select-native {
            position: absolute !important;
            inset: 0 !important;
            width: 100% !important;
            height: 100% !important;
            opacity: 0 !important;
            pointer-events: none !important;
        }
        .staff-select-trigger {
            width: 100%;
            min-width: 0;
            display: inline-flex;
            align-items: center;
            justify-content: space-between;
            gap: 10px;
            padding: 7px 10px;
            border: 1px solid #d8e1e8;
            border-radius: 7px;
            background: #ffffff;
            color: #173042;
            font-family: var(--font-body);
            font-size: 12.5px;
            font-weight: 500;
            line-height: 1.35;
            text-align: left;
            cursor: pointer;
            transition: border-color 0.15s ease, box-shadow 0.15s ease, background 0.15s ease;
        }
        .staff-select-trigger:hover { border-color: #9bb4c6; background: #fbfdff; }
        .staff-select-trigger:focus-visible,
        .staff-select.is-open .staff-select-trigger {
            border-color: #0f6b8f;
            box-shadow: 0 0 0 3px rgba(15, 107, 143, 0.12);
            outline: none;
        }
        .staff-select--underline .staff-select-trigger {
            padding: 5px 20px 5px 0;
            border: 0;
            border-bottom: 1px solid #cbd5e1;
            border-radius: 0;
            background: transparent;
            box-shadow: none;
        }
        .staff-select--underline .staff-select-trigger:hover,
        .staff-select--underline.is-open .staff-select-trigger,
        .staff-select--underline .staff-select-trigger:focus-visible { border-bottom-color: #00684a; }
        .staff-select-chevron { flex: 0 0 auto; color: #647b8a; font-size: 10px; transition: transform 0.15s ease; }
        .staff-select.is-open .staff-select-chevron { transform: rotate(180deg); }
        .staff-select-options {
            position: absolute;
            top: calc(100% + 5px);
            left: 0;
            right: 0;
            z-index: 20000;
            min-width: max(100%, 190px);
            max-width: min(320px, calc(100vw - 24px));
            max-height: min(280px, 50vh);
            overflow-y: auto;
            padding: 4px;
            border: 1px solid #dce5ec;
            border-radius: 8px;
            background: #ffffff;
            box-shadow: 0 12px 28px rgba(15, 35, 52, 0.16), 0 2px 6px rgba(15, 35, 52, 0.06);
        }
        .staff-select-options[hidden] { display: none; }
        .staff-select-option {
            width: 100%;
            min-height: 32px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
            padding: 6px 9px;
            border: 0;
            border-radius: 5px;
            background: transparent;
            color: #243b4b;
            font: 500 12.5px/1.35 var(--font-body);
            text-align: left;
            cursor: pointer;
        }
        .staff-select-option:hover,
        .staff-select-option.is-active { background: #eff6fa; color: #0f4c81; }
        .staff-select-option[aria-selected="true"] { background: #e8f3f8; color: #0f4c81; font-weight: 700; }
        .staff-select-option:disabled { color: #94a3b8; cursor: not-allowed; }
        .staff-select-group-label { padding: 7px 9px 4px; color: #8495a2; font-size: 10px; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; }

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
        .top-header > #toast-container {
            position: static !important;
            inset: auto !important;
            z-index: 1100 !important;
            display: flex !important;
            flex: 0 1 auto !important;
            align-items: center !important;
            justify-content: flex-end !important;
            min-width: 0 !important;
            width: min(520px, 42vw) !important;
            max-width: 520px !important;
            margin: 0 12px 0 auto !important;
            overflow: hidden !important;
            pointer-events: none !important;
        }
        .top-header > #toast-container > div {
            position: static !important;
            inset: auto !important;
            flex: 0 1 100% !important;
            margin-left: auto !important;
            width: max-content !important;
            min-width: 0 !important;
            max-width: 100% !important;
            height: 34px !important;
            min-height: 34px !important;
            padding: 6px 11px !important;
            border-radius: 7px !important;
            font-size: 12px !important;
            line-height: 1.35 !important;
            box-shadow: 0 4px 12px rgba(0, 20, 40, 0.2) !important;
            pointer-events: auto !important;
        }
        .top-header > #toast-container > div > span:first-child {
            min-width: 0;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        .top-header > #toast-container > div > span:last-child { flex: 0 0 auto; }
        #lang-dropdown-menu {
            padding: 4px !important;
            border: 1px solid #dce5ec !important;
            border-radius: 8px !important;
            box-shadow: 0 12px 28px rgba(15, 35, 52, 0.16) !important;
        }
        #lang-dropdown-menu > div {
            border: 0 !important;
            border-radius: 5px;
            color: #243b4b;
            cursor: pointer;
            transition: background 0.12s ease, color 0.12s ease;
        }
        #lang-dropdown-menu > div:hover { background: #eff6fa; color: #0f4c81; }
        @media (max-width: 760px) {
            .top-header { padding-left: 12px !important; padding-right: 12px !important; }
            .header-left { gap: 8px; }
            .header-right { gap: 10px; }
            .top-header > #toast-container { width: min(320px, 32vw) !important; margin: 0 6px 0 auto !important; }
            .top-header > #toast-container > div { max-width: 180px !important; }
        }
        @media (max-width: 520px) {
            .brand-logo { font-size: 0 !important; gap: 0 !important; }
            .brand-logo i { font-size: 17px !important; }
            .project-selector { max-width: 132px; overflow: hidden; white-space: nowrap; }
            .top-header > #toast-container { position: fixed !important; top: 56px !important; left: auto !important; right: 12px !important; width: min(360px, calc(100vw - 24px)) !important; max-width: calc(100vw - 24px) !important; transform: none; margin: 0 !important; }
        }
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
    const APPLICATION_NAV_GROUPS = window.AIP_APPLICATION_NAV_GROUPS;

    function getNavSectionStateKey(headerEl) {
        const sectionName = headerEl.querySelector('span')?.textContent?.trim().toLowerCase();
        return `aip_staff_nav_section_${sectionName || 'unknown'}`;
    }

    function toggleNavSection(headerEl) {
        const navList = headerEl.nextElementSibling;
        const icon = headerEl.querySelector('.toggle-icon');
        if (navList) {
            if (navList.style.display === 'none') {
                navList.style.display = 'block';
                if (icon) icon.style.transform = 'rotate(0deg)';
                sessionStorage.setItem(getNavSectionStateKey(headerEl), 'open');
            } else {
                navList.style.display = 'none';
                if (icon) icon.style.transform = 'rotate(-90deg)';
                sessionStorage.setItem(getNavSectionStateKey(headerEl), 'closed');
            }
        }
    }

    function setActiveApplicationCategory(navList, categoryId) {
        navList.querySelectorAll('.app-category').forEach(group => {
            const button = group.querySelector('.app-category-toggle');
            const items = group.querySelector('.app-category-items');
            const isActive = group.dataset.category === categoryId;
            button.setAttribute('aria-expanded', String(isActive));
            items.hidden = !isActive;
        });
        if (categoryId) sessionStorage.setItem('aip_staff_application_category', categoryId);
        else sessionStorage.removeItem('aip_staff_application_category');
    }

    function ensureApplicationsNavigationSection() {
        const sidebar = document.querySelector('.sidebar');
        if (!sidebar) return null;

        const existingSection = Array.from(sidebar.querySelectorAll('.nav-section')).find(section =>
            section.querySelector('.section-title span')?.textContent
                ?.trim().toLowerCase().includes('applications')
        );
        if (existingSection) return existingSection;

        const section = document.createElement('div');
        section.className = 'nav-section';
        section.innerHTML = `
            <div class="section-title">
                <span><i class="fa-solid fa-layer-group" aria-hidden="true"></i> Applications</span>
                <i class="fa-solid fa-chevron-down toggle-icon" aria-hidden="true"></i>
            </div>
            <ul class="nav-list"></ul>
        `;
        const sections = Array.from(sidebar.querySelectorAll('.nav-section'));
        const consoleSection = sections.find(item =>
            item.querySelector('.section-title span')?.textContent
                ?.trim().toLowerCase().includes('console')
        ) || sections[0];
        if (consoleSection) consoleSection.after(section);
        else sidebar.prepend(section);
        return section;
    }

    function syncApplicationsNavigation(path) {
        const applicationsSection = ensureApplicationsNavigationSection();
        const navList = applicationsSection?.querySelector('.nav-list');
        if (!applicationsSection || !navList) return false;

        const activeItem = APPLICATION_NAV_GROUPS
            .flatMap(group => group.items.map(item => ({ group, item })))
            .find(({ item }) => path.endsWith(`/apis/${item[2].toLowerCase()}`));
        const storedCategory = sessionStorage.getItem('aip_staff_application_category');
        const selectedCategory = activeItem?.group.id ||
            APPLICATION_NAV_GROUPS.find(group => group.id === storedCategory)?.id ||
            APPLICATION_NAV_GROUPS[0].id;

        navList.replaceChildren();
        APPLICATION_NAV_GROUPS.forEach(group => {
            const groupItem = document.createElement('li');
            groupItem.className = 'app-category';
            groupItem.dataset.category = group.id;

            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'app-category-toggle';
            button.setAttribute('aria-expanded', 'false');
            button.innerHTML = `
                <span class="app-category-label">${group.label}</span>
                <i class="fa-solid fa-chevron-down app-category-chevron" aria-hidden="true"></i>
            `;
            button.addEventListener('click', () => {
                const isExpanded = button.getAttribute('aria-expanded') === 'true';
                setActiveApplicationCategory(navList, isExpanded ? null : group.id);
            });

            const childList = document.createElement('ul');
            childList.className = 'nav-list app-category-items';
            group.items.forEach(([label, icon, href]) => {
                const item = document.createElement('li');
                item.className = 'nav-item';
                if (activeItem?.item[2] === href) item.classList.add('active');
                const link = document.createElement('a');
                link.href = window.aipProjectApiHref(href);
                const iconElement = document.createElement('i');
                iconElement.className = `fa-solid ${icon}`;
                link.append(iconElement, document.createTextNode(label));
                item.appendChild(link);
                childList.appendChild(item);
            });

            groupItem.append(button, childList);
            navList.appendChild(groupItem);
        });

        setActiveApplicationCategory(navList, selectedCategory);
        return Boolean(activeItem);
    }

    function setSidebarCollapsed(collapsed) {
            document.body.classList.toggle('staff-sidebar-collapsed', collapsed);
            localStorage.setItem('aip_staff_sidebar_collapsed', String(collapsed));
            const toggle = document.getElementById('staff-sidebar-toggle');
            if (toggle) {
                toggle.setAttribute('aria-expanded', String(!collapsed));
                toggle.setAttribute('aria-label', collapsed ? 'Expand sidebar' : 'Collapse sidebar');
                toggle.title = collapsed ? 'Expand sidebar' : 'Collapse sidebar';
            }
        }

    function ensureHeaderControls() {
            const header = document.querySelector('.top-header');
            if (!header) return;

            const headerLeft = header.querySelector('.header-left');
            const brand = headerLeft?.querySelector('.brand-logo');
            if (headerLeft && brand && !document.getElementById('staff-sidebar-toggle')) {
                const toggle = document.createElement('button');
                toggle.id = 'staff-sidebar-toggle';
                toggle.type = 'button';
                toggle.className = 'sidebar-toggle';
                toggle.innerHTML = '<i class="fa-solid fa-bars" aria-hidden="true"></i>';
                toggle.addEventListener('click', () => {
                    setSidebarCollapsed(!document.body.classList.contains('staff-sidebar-collapsed'));
                });
                headerLeft.insertBefore(toggle, brand);
            }
            setSidebarCollapsed(localStorage.getItem('aip_staff_sidebar_collapsed') === 'true');

            let toastContainer = document.getElementById('toast-container');
            if (!toastContainer) {
                toastContainer = document.createElement('div');
                toastContainer.id = 'toast-container';
            }
            const headerRight = header.querySelector('.header-right');
            header.insertBefore(toastContainer, headerRight || null);
        }

    const enhancedSelects = new WeakSet();
    let selectOptionsSequence = 0;

    function enhanceSelect(select) {
            if (enhancedSelects.has(select) || select.multiple || select.size > 1) return;
            enhancedSelects.add(select);

            const computed = window.getComputedStyle(select);
            const wrapper = document.createElement('div');
            wrapper.className = 'staff-select';
            wrapper.style.setProperty('--staff-select-width', computed.width === 'auto' ? 'auto' : computed.width);
            if (select.classList.contains('filter-input') ||
                select.classList.contains('filter-select') ||
                computed.borderTopWidth === '0px') {
                wrapper.classList.add('staff-select--underline');
            }

            const trigger = document.createElement('button');
            trigger.type = 'button';
            trigger.className = 'staff-select-trigger';
            trigger.setAttribute('role', 'combobox');
            trigger.setAttribute('aria-haspopup', 'listbox');
            trigger.setAttribute('aria-expanded', 'false');
            const label = select.labels?.[0]?.textContent?.trim() ||
                select.getAttribute('aria-label') ||
                select.options[select.selectedIndex]?.textContent?.trim() ||
                'Select option';
            if (label) trigger.setAttribute('aria-label', label);
            if (computed.height !== 'auto') trigger.style.height = computed.height;
            trigger.style.fontFamily = computed.fontFamily;
            trigger.style.fontSize = computed.fontSize;
            trigger.style.fontWeight = computed.fontWeight;
            trigger.style.color = computed.color;
            if (select.style.cssText) {
                trigger.style.cssText += `;${select.style.cssText}`;
            }
            trigger.style.setProperty('background-image', 'none', 'important');
            trigger.style.setProperty('appearance', 'none', 'important');
            trigger.style.setProperty('-webkit-appearance', 'none', 'important');
            trigger.classList.add(...Array.from(select.classList).filter(name => name !== 'staff-select-native'));

            const selectedText = document.createElement('span');
            selectedText.className = 'staff-select-value';
            const chevron = document.createElement('i');
            chevron.className = 'fa-solid fa-chevron-down staff-select-chevron';
            chevron.setAttribute('aria-hidden', 'true');
            trigger.append(selectedText, chevron);

            const list = document.createElement('div');
            list.className = 'staff-select-options';
            list.id = `staff-select-options-${++selectOptionsSequence}`;
            list.setAttribute('role', 'listbox');
            trigger.setAttribute('aria-controls', list.id);
            list.hidden = true;

            wrapper.append(trigger, list);
            select.parentNode.insertBefore(wrapper, select);
            wrapper.insertBefore(select, trigger);
            select.classList.add('staff-select-native');
            select.tabIndex = -1;
            select.setAttribute('aria-hidden', 'true');

            let activeIndex = Math.max(0, select.selectedIndex);
            const options = () => Array.from(select.options);
            const syncValue = () => {
                const selected = select.selectedOptions[0];
                selectedText.textContent = selected?.textContent?.trim() || 'Select…';
                trigger.disabled = select.disabled;
                trigger.setAttribute('aria-valuetext', selectedText.textContent);
            };
            const close = (restoreFocus = false) => {
                list.hidden = true;
                wrapper.classList.remove('is-open');
                trigger.setAttribute('aria-expanded', 'false');
                if (restoreFocus) trigger.focus();
            };
            const choose = (index) => {
                const option = options()[index];
                if (!option || option.disabled) return;
                select.selectedIndex = index;
                select.dispatchEvent(new Event('input', { bubbles: true }));
                select.dispatchEvent(new Event('change', { bubbles: true }));
                syncValue();
                close(true);
            };
            const renderOptions = () => {
                list.replaceChildren();
                options().forEach((option, index) => {
                    if (option.parentElement instanceof HTMLOptGroupElement &&
                        option.parentElement.label &&
                        options().indexOf(option) === Array.from(option.parentElement.children).findIndex(child => child === option)) {
                        const groupLabel = document.createElement('div');
                        groupLabel.className = 'staff-select-group-label';
                        groupLabel.textContent = option.parentElement.label;
                        list.appendChild(groupLabel);
                    }
                    const optionButton = document.createElement('button');
                    optionButton.type = 'button';
                    optionButton.className = 'staff-select-option';
                    optionButton.setAttribute('role', 'option');
                    optionButton.setAttribute('aria-selected', String(index === select.selectedIndex));
                    optionButton.disabled = option.disabled || option.parentElement instanceof HTMLOptGroupElement && option.parentElement.disabled;
                    optionButton.classList.toggle('is-active', index === activeIndex);
                    optionButton.textContent = option.textContent?.trim() || '';
                    optionButton.addEventListener('mousedown', event => event.preventDefault());
                    optionButton.addEventListener('click', () => choose(index));
                    list.appendChild(optionButton);
                });
            };
            const open = () => {
                if (trigger.disabled) return;
                syncValue();
                activeIndex = Math.max(0, select.selectedIndex);
                renderOptions();
                list.hidden = false;
                wrapper.classList.add('is-open');
                trigger.setAttribute('aria-expanded', 'true');
            };

            trigger.addEventListener('click', () => {
                if (list.hidden) open();
                else close();
            });
            trigger.addEventListener('keydown', event => {
                const optionList = options();
                if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
                    event.preventDefault();
                    if (list.hidden) open();
                    else {
                        const direction = event.key === 'ArrowDown' ? 1 : -1;
                        activeIndex = (activeIndex + direction + optionList.length) % optionList.length;
                        renderOptions();
                        list.querySelectorAll('.staff-select-option')[activeIndex]?.scrollIntoView({ block: 'nearest' });
                    }
                } else if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    if (list.hidden) open();
                    else choose(activeIndex);
                } else if (event.key === 'Escape' && !list.hidden) {
                    event.preventDefault();
                    close(true);
                } else if (event.key === 'Home' && !list.hidden) {
                    event.preventDefault();
                    activeIndex = 0;
                    renderOptions();
                } else if (event.key === 'End' && !list.hidden) {
                    event.preventDefault();
                    activeIndex = optionList.length - 1;
                    renderOptions();
                }
            });
            select.addEventListener('change', syncValue);
            syncValue();
        }

    function enhanceSelects(root = document) {
            if (root instanceof HTMLSelectElement) enhanceSelect(root);
            root.querySelectorAll?.('select').forEach(enhanceSelect);
        }

    let selectObserver = null;

    function observeDynamicSelects() {
            if (selectObserver || !document.body) return;
            selectObserver = new MutationObserver(records => {
                records.forEach(record => {
                    record.addedNodes.forEach(node => {
                        if (node instanceof Element) enhanceSelects(node);
                    });
                });
            });
            selectObserver.observe(document.body, { childList: true, subtree: true });
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
        const isApplicationRoute = syncApplicationsNavigation(path);

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

        document.querySelectorAll('.sidebar .section-title').forEach(header => {
            header.onclick = () => toggleNavSection(header);
            const navList = header.nextElementSibling;
            if (!navList) return;

            const savedState = sessionStorage.getItem(getNavSectionStateKey(header));
            const isApplicationsSection = header.querySelector('span')?.textContent
                ?.trim().toLowerCase().includes('applications');
            const isOpen = isApplicationRoute && isApplicationsSection
                ? true
                : savedState === 'open';

            navList.style.display = isOpen ? 'block' : 'none';
            const icon = header.querySelector('.toggle-icon');
            if (icon) icon.style.transform = isOpen ? 'rotate(0deg)' : 'rotate(-90deg)';
        });

    }

    let navigationController = null;

    function isStaffPageUrl(url) {
        return url.origin === window.location.origin &&
            (/^\/staff(?:\/|$)/i.test(url.pathname) || /^\/project\//i.test(url.pathname));
    }

    async function runPageScripts(parsedPage, pageUrl) {
        const scripts = Array.from(parsedPage.querySelectorAll('script'));
        for (const sourceScript of scripts) {
            const source = sourceScript.getAttribute('src');
            if (source) {
                const scriptUrl = new URL(source, pageUrl);
                if (scriptUrl.pathname.endsWith('/staff_layout.js')) continue;
                if (Array.from(document.scripts).some(script => script.src === scriptUrl.href)) continue;

                await new Promise((resolve, reject) => {
                    const script = document.createElement('script');
                    script.src = scriptUrl.href;
                    script.async = false;
                    script.onload = resolve;
                    script.onerror = () => reject(new Error(`Failed to load page script: ${scriptUrl.href}`));
                    document.body.appendChild(script);
                });
                continue;
            }

            const code = sourceScript.textContent || '';
            const functionNames = Array.from(
                code.matchAll(/(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(/g),
                match => match[1]
            );
            const exposeFunctions = [...new Set(functionNames)]
                .map(name => `if (typeof ${name} === "function") window[${JSON.stringify(name)}] = ${name};`)
                .join('\n');
            const moduleSource = `${code}\n${exposeFunctions}`;
            const moduleUrl = URL.createObjectURL(new Blob([moduleSource], { type: 'text/javascript' }));
            try {
                await import(moduleUrl);
            } finally {
                URL.revokeObjectURL(moduleUrl);
            }
        }
    }

    async function loadStaffPage(url, { addHistory = false } = {}) {
        navigationController?.abort();
        const controller = new AbortController();
        navigationController = controller;

        try {
            const response = await fetch(url.href, {
                credentials: 'same-origin',
                signal: controller.signal
            });
            if (!response.ok) {
                throw new Error(`Unable to open page (${response.status})`);
            }

            const finalUrl = new URL(response.url);
            if (!isStaffPageUrl(finalUrl)) {
                window.location.assign(finalUrl.href);
                return;
            }

            const parsedPage = new DOMParser().parseFromString(await response.text(), 'text/html');
            if (!parsedPage.body || !parsedPage.querySelector('.layout-body')) {
                throw new Error('The destination page does not use the staff portal layout');
            }

            const pageStyles = Array.from(parsedPage.head.querySelectorAll('style'));
            document.head.querySelectorAll('style:not(#staff-shared-layout-css)').forEach(style => style.remove());
            pageStyles.forEach(style => document.head.appendChild(style.cloneNode(true)));
            const sharedStyles = document.getElementById('staff-shared-layout-css');
            if (sharedStyles) document.head.appendChild(sharedStyles);

            const bodyNodes = Array.from(parsedPage.body.childNodes)
                .filter(node => !(node instanceof HTMLScriptElement));
            document.body.replaceChildren(...bodyNodes.map(node => document.importNode(node, true)));
            document.title = parsedPage.title;

            if (addHistory) {
                window.history.pushState({ staffPage: true }, '', finalUrl.href);
            }
            StaffLayout.init();
            await runPageScripts(parsedPage, finalUrl);
            window.scrollTo(0, 0);
        } catch (error) {
            if (error.name === 'AbortError') return;
            console.error('Staff page navigation failed:', error);
            showToast('Không thể mở trang. Vui lòng thử lại.', 'error');
        } finally {
            if (navigationController === controller) navigationController = null;
        }
    }

    function handleStaffNavigation(event) {
        const anchor = event.target instanceof Element
            ? event.target.closest('.sidebar a, .top-header .brand-logo')
            : null;
        if (!(anchor instanceof HTMLAnchorElement) ||
            event.defaultPrevented ||
            event.button !== 0 ||
            event.metaKey || event.ctrlKey || event.shiftKey || event.altKey ||
            (anchor.target && anchor.target !== '_self') ||
            anchor.hasAttribute('download')) {
            return;
        }

        const url = new URL(anchor.href, window.location.href);
        if (!isStaffPageUrl(url) || url.href === window.location.href) return;

        event.preventDefault();
        loadStaffPage(url, { addHistory: true });
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
            ensureHeaderControls();
            syncTopbarAndSidebar();
            checkMandatoryAuth();
            enhanceSelects(document.body);
            observeDynamicSelects();
            document.querySelectorAll('.top-header .project-selector').forEach(selector => {
                selector.onclick = openSelectProjectModal;
            });
            if (!window.__aipStaffNavigationBound) {
                document.addEventListener('click', (event) => {
                    const target = event.target;
                    const menu = document.getElementById('lang-dropdown-menu');
                    if (menu && target instanceof Element &&
                        !target.closest('#lang-dropdown-menu') &&
                        !target.closest('.header-right')) {
                        menu.style.display = 'none';
                    }
                    if (!(target instanceof Element) || !target.closest('.staff-select')) {
                        document.querySelectorAll('.staff-select.is-open').forEach(wrapper => {
                            wrapper.classList.remove('is-open');
                            const list = wrapper.querySelector('.staff-select-options');
                            const trigger = wrapper.querySelector('.staff-select-trigger');
                            if (list) list.hidden = true;
                            if (trigger) trigger.setAttribute('aria-expanded', 'false');
                        });
                    }
                    handleStaffNavigation(event);
                }, { capture: true });
                window.addEventListener('popstate', () => {
                    const url = new URL(window.location.href);
                    if (isStaffPageUrl(url)) loadStaffPage(url);
                });
                window.__aipStaffNavigationBound = true;
            }
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
