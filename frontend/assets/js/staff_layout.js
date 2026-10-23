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
            --font-body: 'Outfit', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            --font-code: 'Fira Code', monospace;
            --brand-50: #ecf3ff;
            --brand-100: #dde9ff;
            --brand-500: #465fff;
            --brand-600: #3641f5;
            --gray-25: #fcfcfd;
            --gray-50: #f9fafb;
            --gray-100: #f2f4f7;
            --gray-200: #e4e7ec;
            --gray-300: #d0d5dd;
            --gray-400: #98a2b3;
            --gray-500: #667085;
            --gray-600: #475467;
            --gray-700: #344054;
            --gray-800: #1d2939;
            --gray-900: #101828;
            --bg-page: #f9fafb;
            --sidebar-bg: #ffffff;
            --border-color: #e4e7ec;
            --primary: #465fff;
            --primary-hover: #3641f5;
        }

        /* Top Header - TailAdmin Clean Style */
        .top-header {
            background: #ffffff !important;
            height: 56px !important;
            min-height: 56px !important;
            max-height: 56px !important;
            padding: 0 24px !important;
            display: flex !important;
            align-items: center !important;
            justify-content: space-between !important;
            color: #101828 !important;
            font-size: 14px !important;
            position: sticky !important;
            top: 0 !important;
            z-index: 1000 !important;
            border-bottom: 1px solid #e4e7ec !important;
            font-family: var(--font-body);
            box-shadow: 0 1px 2px rgba(16, 24, 40, 0.04) !important;
        }
        .header-left {
            display: flex !important;
            align-items: center !important;
            gap: 16px !important;
            flex-shrink: 0 !important;
        }
        .sidebar-toggle {
            width: 36px !important;
            height: 36px !important;
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
            border: 1px solid #e4e7ec !important;
            border-radius: 8px !important;
            background: #ffffff !important;
            color: #667085 !important;
            font-size: 14px !important;
            cursor: pointer !important;
            transition: all 0.15s ease !important;
            flex-shrink: 0 !important;
        }
        .sidebar-toggle:hover,
        .sidebar-toggle:focus-visible {
            background: #f2f4f7 !important;
            border-color: #d0d5dd !important;
            color: #101828 !important;
            outline: none !important;
        }
        .brand-logo {
            font-family: var(--font-heading);
            font-size: 18px !important;
            font-weight: 800 !important;
            color: #101828 !important;
            text-decoration: none !important;
            display: flex !important;
            align-items: center !important;
            gap: 8px !important;
            letter-spacing: -0.02em !important;
        }
        .brand-logo i {
            color: #465fff !important;
            font-size: 19px !important;
        }
        .project-selector {
            background: #f9fafb !important;
            border: 1px solid #e4e7ec !important;
            border-radius: 8px !important;
            padding: 6px 12px !important;
            font-size: 12.5px !important;
            font-weight: 500 !important;
            cursor: pointer !important;
            display: flex !important;
            align-items: center !important;
            gap: 8px !important;
            color: #344054 !important;
            transition: all 0.15s ease !important;
        }
        .project-selector:hover {
            background: #f2f4f7 !important;
            border-color: #d0d5dd !important;
            color: #101828 !important;
        }
        .project-selector i {
            color: #667085 !important;
        }

        .header-right {
            display: flex !important;
            align-items: center !important;
            gap: 16px !important;
        }
        .lang-dropdown-container {
            position: relative !important;
            cursor: pointer !important;
            display: flex !important;
            align-items: center !important;
            gap: 6px !important;
            font-size: 13px !important;
            font-weight: 500 !important;
            color: #475467 !important;
            padding: 6px 10px !important;
            border-radius: 8px !important;
            transition: all 0.15s ease !important;
        }
        .lang-dropdown-container:hover {
            background: #f2f4f7 !important;
            color: #101828 !important;
        }
        .lang-dropdown-container i {
            color: #667085 !important;
        }
        .user-menu {
            display: flex !important;
            align-items: center !important;
            gap: 8px !important;
            font-weight: 500 !important;
            color: #344054 !important;
            font-size: 13.5px !important;
            padding: 4px 8px !important;
            border-radius: 8px !important;
            transition: background 0.15s ease !important;
        }
        .user-menu:hover {
            background: #f2f4f7 !important;
        }
        .user-menu .user-avatar {
            width: 32px !important;
            height: 32px !important;
            border-radius: 50% !important;
            background: #ecf3ff !important;
            color: #465fff !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            font-weight: 700 !important;
            font-size: 13px !important;
        }
        .user-menu i.fa-right-from-bracket {
            color: #98a2b3 !important;
            transition: color 0.15s ease !important;
        }
        .user-menu i.fa-right-from-bracket:hover {
            color: #f04438 !important;
        }

        html {
            overflow-y: scroll !important;
        }
        body {
            font-size: 14px !important;
            line-height: 1.5 !important;
            background: #f9fafb !important;
            color: #101828 !important;
            font-family: var(--font-body);
        }
        .layout-body {
            display: flex !important;
            flex: 1 !important;
            min-height: calc(100vh - 56px) !important;
        }

        /* Sidebar Standard - TailAdmin Vue Style */
        .sidebar {
            width: 260px !important;
            min-width: 260px !important;
            max-width: 260px !important;
            background: #ffffff !important;
            border-right: 1px solid #e4e7ec !important;
            padding: 16px 0 24px 0 !important;
            position: sticky !important;
            top: 56px !important;
            height: calc(100vh - 56px) !important;
            max-height: calc(100vh - 56px) !important;
            align-self: flex-start !important;
            overflow-y: auto !important;
            overflow-x: hidden !important;
            flex-shrink: 0 !important;
            box-sizing: border-box !important;
            font-family: var(--font-body);
            transition: width 0.2s ease, min-width 0.2s ease, max-width 0.2s ease, padding 0.2s ease, border-color 0.2s ease;
        }
        .sidebar::-webkit-scrollbar {
            width: 4px;
        }
        .sidebar::-webkit-scrollbar-thumb {
            background: #e4e7ec;
            border-radius: 4px;
        }
        .sidebar::-webkit-scrollbar-thumb:hover {
            background: #d0d5dd;
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
            background: #f9fafb !important;
        }
        .nav-section {
            margin-bottom: 8px !important;
        }
        .section-title {
            font-size: 11px !important;
            font-weight: 600 !important;
            text-transform: uppercase !important;
            color: #98a2b3 !important;
            padding: 14px 18px 6px 18px !important;
            letter-spacing: 0.06em !important;
            display: flex !important;
            align-items: center !important;
            justify-content: space-between !important;
            cursor: pointer !important;
            user-select: none !important;
            transition: color 0.15s ease;
        }
        .section-title:hover {
            color: #465fff !important;
        }
        .section-title span {
            display: flex !important;
            align-items: center !important;
            gap: 8px !important;
        }
        .section-title .toggle-icon {
            font-size: 10px !important;
            transition: transform 0.2s ease !important;
            color: #98a2b3 !important;
        }
        .nav-list {
            list-style: none !important;
            margin: 0 !important;
            padding: 0 !important;
        }
        .app-category {
            list-style: none !important;
        }
        .app-category-toggle {
            width: calc(100% - 24px) !important;
            min-height: 38px !important;
            margin: 2px 12px !important;
            padding: 8px 12px !important;
            display: flex !important;
            align-items: center !important;
            justify-content: space-between !important;
            gap: 8px !important;
            border: none !important;
            border-radius: 8px !important;
            background: transparent !important;
            color: #344054 !important;
            font: 500 13.5px/1.4 var(--font-body) !important;
            text-align: left !important;
            cursor: pointer !important;
            transition: all 0.15s ease !important;
        }
        .app-category-toggle:hover {
            background: #f2f4f7 !important;
            color: #101828 !important;
        }
        .app-category-toggle[aria-expanded="true"] {
            background: #ecf3ff !important;
            color: #465fff !important;
            font-weight: 600 !important;
        }
        .app-category-label {
            min-width: 0 !important;
        }
        .app-category-chevron {
            color: #98a2b3 !important;
            font-size: 10px !important;
            transition: transform 0.2s ease !important;
        }
        .app-category-toggle[aria-expanded="true"] .app-category-chevron {
            transform: rotate(180deg) !important;
            color: #465fff !important;
        }
        .app-category-items[hidden] {
            display: none !important;
        }
        .app-category-items .nav-item a {
            margin: 2px 12px 2px 20px !important;
            padding: 8px 12px !important;
            border-radius: 8px !important;
            font-size: 13.5px !important;
        }
        .nav-item a {
            display: flex !important;
            align-items: center !important;
            gap: 12px !important;
            margin: 2px 12px !important;
            padding: 8.5px 12px !important;
            border-radius: 8px !important;
            font-size: 14px !important;
            font-weight: 500 !important;
            color: #344054 !important;
            text-decoration: none !important;
            border: none !important;
            border-left: none !important;
            background: transparent !important;
            transition: all 0.15s ease !important;
        }
        .nav-item a i {
            color: #667085 !important;
            font-size: 15px !important;
            width: 20px !important;
            text-align: center !important;
            transition: color 0.15s ease !important;
            flex-shrink: 0 !important;
        }
        .nav-item a:hover {
            background: #f2f4f7 !important;
            color: #101828 !important;
        }
        .nav-item a:hover i {
            color: #344054 !important;
        }
        .nav-item.active a {
            background: #ecf3ff !important;
            color: #465fff !important;
            font-weight: 600 !important;
            border: none !important;
            border-left: none !important;
        }
        .nav-item.active a i {
            color: #465fff !important;
        }
        .nav-direct-link a {
            display: flex !important;
            align-items: center !important;
            gap: 12px !important;
            margin: 2px 12px !important;
            padding: 8.5px 12px !important;
            border-radius: 8px !important;
            font-size: 13px !important;
            font-weight: 600 !important;
            text-transform: uppercase !important;
            letter-spacing: 0.04em !important;
            color: #475467 !important;
            text-decoration: none !important;
            border: none !important;
            border-left: none !important;
            background: transparent !important;
            transition: all 0.15s ease !important;
        }
        .nav-direct-link a i {
            color: #667085 !important;
            font-size: 14px !important;
            width: 20px !important;
            text-align: center !important;
            transition: color 0.15s ease !important;
            flex-shrink: 0 !important;
        }
        .nav-direct-link a:hover {
            background: #f2f4f7 !important;
            color: #101828 !important;
        }
        .nav-direct-link a:hover i {
            color: #344054 !important;
        }
        .nav-direct-link.active a {
            background: #ecf3ff !important;
            color: #465fff !important;
            font-weight: 700 !important;
            border: none !important;
            border-left: none !important;
        }
        .nav-direct-link.active a i {
            color: #465fff !important;
        }

        /* TailAdmin Modern Card & Table Tokens */
        .tail-card {
            background: #ffffff !important;
            border: 1px solid #e4e7ec !important;
            border-radius: 12px !important;
            box-shadow: 0 1px 3px rgba(16, 24, 40, 0.04) !important;
            overflow: hidden !important;
        }
        .tail-btn-primary {
            background: #465fff !important;
            color: #ffffff !important;
            border: 1px solid #465fff !important;
            border-radius: 8px !important;
            padding: 8px 16px !important;
            font-size: 13.5px !important;
            font-weight: 500 !important;
            cursor: pointer !important;
            transition: all 0.15s ease !important;
            display: inline-flex !important;
            align-items: center !important;
            gap: 8px !important;
        }
        .tail-btn-primary:hover {
            background: #3641f5 !important;
            border-color: #3641f5 !important;
        }
        .tail-btn-secondary {
            background: #ffffff !important;
            color: #344054 !important;
            border: 1px solid #d0d5dd !important;
            border-radius: 8px !important;
            padding: 8px 16px !important;
            font-size: 13.5px !important;
            font-weight: 500 !important;
            cursor: pointer !important;
            transition: all 0.15s ease !important;
            display: inline-flex !important;
            align-items: center !important;
            gap: 8px !important;
        }
        .tail-btn-secondary:hover {
            background: #f9fafb !important;
            border-color: #98a2b3 !important;
            color: #101828 !important;
        }
        .tail-input {
            width: 100% !important;
            border: 1px solid #d0d5dd !important;
            border-radius: 8px !important;
            background: #ffffff !important;
            padding: 8px 14px !important;
            font-size: 14px !important;
            color: #101828 !important;
            outline: none !important;
            transition: border-color 0.15s ease, box-shadow 0.15s ease !important;
        }
        .tail-input:focus {
            border-color: #465fff !important;
            box-shadow: 0 0 0 3px rgba(70, 95, 255, 0.12) !important;
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
        .staff-select.is-dropup .staff-select-options,
        .staff-select--dropup .staff-select-options {
            top: auto !important;
            bottom: calc(100% + 5px) !important;
            box-shadow: 0 -12px 28px rgba(15, 35, 52, 0.16), 0 -2px 6px rgba(15, 35, 52, 0.06) !important;
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

        /* Direct links styled via TailAdmin */

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
            white-space: nowrap;
        }
        .proj-table td {
            padding: 12px 18px;
            border-bottom: 1px solid #f4f6f5;
            color: #001e2b;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
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
            flex-direction: row !important;
            align-items: center !important;
            justify-content: flex-end !important;
            min-width: 0 !important;
            width: min(520px, 42vw) !important;
            max-width: 520px !important;
            height: 36px !important;
            max-height: 36px !important;
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
            max-height: 34px !important;
            padding: 6px 11px !important;
            border-radius: 7px !important;
            font-size: 12px !important;
            line-height: 1.35 !important;
            box-shadow: 0 4px 12px rgba(0, 20, 40, 0.2) !important;
            pointer-events: auto !important;
            animation: aipToastSlideIn 0.22s cubic-bezier(0.16, 1, 0.3, 1) !important;
        }
        .top-header > #toast-container > div > span:first-child {
            min-width: 0;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        .top-header > #toast-container > div > span:last-child { flex: 0 0 auto; }
        @keyframes aipToastSlideIn {
            from { opacity: 0; transform: translateY(-6px) scale(0.97); }
            to { opacity: 1; transform: translateY(0) scale(1); }
        }
        @keyframes aipToastFadeOut {
            from { opacity: 1; transform: translateY(0) scale(1); }
            to { opacity: 0; transform: translateY(-6px) scale(0.97); }
        }
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

    function setActiveProjectName(name, tenantId) {
        localStorage.setItem('aip_active_project', name);
        if (tenantId) {
            localStorage.setItem('aip_active_tenant_id', tenantId);
            localStorage.setItem('aip_active_project_id', tenantId);
        } else {
            const raw = localStorage.getItem('aip_projects');
            if (raw) {
                try {
                    const list = JSON.parse(raw);
                    const found = list.find(p => (p.project_name || '').trim().toLowerCase() === (name || '').trim().toLowerCase());
                    if (found && (found.project_id || found.id)) {
                        const pid = found.project_id || found.id;
                        localStorage.setItem('aip_active_tenant_id', pid);
                        localStorage.setItem('aip_active_project_id', pid);
                    }
                } catch (e) {}
            }
        }
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
                <div class="atlas-modal-box" style="width: 660px; max-width: 95vw;">
                    <div class="atlas-modal-header">Select a project</div>
                    <div class="atlas-modal-body">
                        <div style="display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 20px;">
                            <div style="position: relative; flex: 1;">
                                <input type="text" id="project-search-input" oninput="StaffLayout.filterProjectsList()" placeholder="Search" style="width: 100%; border: none; border-bottom: 1.5px solid #cbd5e1; padding: 8px 32px 8px 0; font-size: 13.5px; outline: none; font-family: var(--font-body); color: #001e2b; background: transparent;">
                                <i class="fa-solid fa-magnifying-glass" style="position: absolute; right: 8px; top: 10px; color: #64748b; font-size: 14px;"></i>
                            </div>
                            <button class="btn-atlas-modal-primary" onclick="StaffLayout.openCreatePrepaidProjectModal()"><i class="fa-solid fa-plus"></i> DỰ ÁN MỚI</button>
                        </div>

                        <div class="proj-table-wrap">
                            <table class="proj-table">
                                <thead>
                                    <tr>
                                        <th style="white-space: nowrap; width: 140px;">Created time</th>
                                        <th style="white-space: nowrap;">Name</th>
                                        <th style="white-space: nowrap; width: 110px; text-align: right;">Type</th>
                                    </tr>
                                </thead>
                                <tbody id="projects-modal-tbody"></tbody>
                            </table>
                        </div>

                        <div style="display: flex; align-items: center; justify-content: flex-end; gap: 16px; font-size: 12px; color: #64748b; user-select: none;">
                            <span>Rows per page</span>
                            <select id="proj-page-size-select" onchange="StaffLayout.changeProjectsPageSize(this.value)" style="border: 1px solid #cbd5e1; border-radius: 4px; padding: 3px 8px; font-size: 12px; outline: none; background: #fff; cursor: pointer; color: #001e2b;">
                                <option value="5" selected>5</option>
                                <option value="10">10</option>
                                <option value="20">20</option>
                            </select>
                            <span id="proj-count-label" style="font-weight: 500; min-width: 90px; text-align: center;">1-5 of 6 riêng</span>
                            <div style="display: inline-flex; align-items: center; gap: 4px;">
                                <button type="button" id="proj-prev-btn" onclick="StaffLayout.prevProjectsPage()" style="border: none; background: transparent; cursor: pointer; padding: 5px 8px; border-radius: 4px; color: #475569; display: flex; align-items: center; justify-content: center; transition: all 0.15s ease;" title="Trang trước">
                                    <i class="fa-solid fa-chevron-left" style="font-size: 11px;"></i>
                                </button>
                                <button type="button" id="proj-next-btn" onclick="StaffLayout.nextProjectsPage()" style="border: none; background: transparent; cursor: pointer; padding: 5px 8px; border-radius: 4px; color: #475569; display: flex; align-items: center; justify-content: center; transition: all 0.15s ease;" title="Trang sau">
                                    <i class="fa-solid fa-chevron-right" style="font-size: 11px;"></i>
                                </button>
                            </div>
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
                    <div class="atlas-modal-header">Tạo Dự Án Mới</div>
                    <div class="atlas-modal-body">
                        <div style="margin-bottom: 16px;">
                            <label style="font-size: 12px; font-weight: 600; color: #5c6c75; display: block; margin-bottom: 4px;">Tên dự án</label>
                            <input type="text" id="input-new-project-name" placeholder="Ví dụ: Dự án AI Doanh Nghiệp" value="" style="width: 100%; border: none; border-bottom: 1.5px solid #cbd5e1; padding: 8px 0; font-size: 13.5px; outline: none; color: #001e2b;">
                        </div>
                        <div>
                            <label style="font-size: 12px; font-weight: 600; color: #5c6c75; display: block; margin-bottom: 4px;">Loại dự án (Billing Type)</label>
                            <select id="input-new-project-type" style="width: 100%; border: none; border-bottom: 1.5px solid #cbd5e1; padding: 8px 0; font-size: 13.5px; outline: none; color: #001e2b; background: transparent;">
                                <option value="prepaid">Prepaid (Quota deduction)</option>
                                <option value="postpaid">Postpaid (Monthly invoice)</option>
                            </select>
                        </div>
                    </div>
                    <div class="atlas-modal-footer">
                        <button class="btn-atlas-modal-cancel" onclick="StaffLayout.closeCreatePrepaidProjectModal()">HỦY</button>
                        <button class="btn-atlas-modal-primary" onclick="StaffLayout.submitCreatePrepaidProject()"><i class="fa-solid fa-plus"></i> TẠO DỰ ÁN</button>
                    </div>
                </div>
            </div>
        `;
        document.body.appendChild(modalContainer);
    }

    // State quản lý phân trang và tìm kiếm danh sách dự án
    let currentProjectsPage = 1;
    let projectsPageSize = 5;
    let currentProjectsFilter = '';
    let cachedProjectsList = [];

    function openSelectProjectModal() {
        const searchInput = document.getElementById('project-search-input');
        if (searchInput) searchInput.value = '';
        currentProjectsFilter = '';
        currentProjectsPage = 1;
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
        cachedProjectsList = projects || [];
        renderProjectsTablePage();
    }

    function renderProjectsTablePage() {
        const tbody = document.getElementById('projects-modal-tbody');
        if (!tbody) return;
        tbody.innerHTML = '';

        const activeName = getActiveProjectName();

        // 1. Dự án Dùng Chung Toàn Hệ Thống (Cố định 1)
        const globalProj = {
            project_id: 'global',
            project_name: 'Dự án Dùng Chung',
            type: 'global',
            created_at: '2026-01-01T00:00:00'
        };

        const isGlobalActive = (
            activeName === globalProj.project_name ||
            activeName === 'Dự án Dùng Chung' ||
            activeName === 'Dự án Dùng Chung (Toàn hệ thống)' ||
            activeName === 'Kho tri thức dùng chung (Toàn hệ thống)' ||
            localStorage.getItem('aip_active_tenant_id') === 'global'
        );
        if (isGlobalActive && (activeName === 'Dự án Dùng Chung (Toàn hệ thống)' || activeName === 'Kho tri thức dùng chung (Toàn hệ thống)')) {
            localStorage.setItem('aip_active_project', 'Dự án Dùng Chung');
            const projLabel = document.getElementById('current-project-label') || document.getElementById('staff-active-project');
            if (projLabel) projLabel.innerText = 'Dự án Dùng Chung';
        }

        // 2. Lọc danh sách Dự án Riêng theo Workspace
        const q = (currentProjectsFilter || '').trim().toLowerCase();
        const allPrivate = (cachedProjectsList || []).filter(p => p.project_id !== 'global' && p.type !== 'global');

        const filteredPrivate = allPrivate.filter(p => {
            if (!q) return true;
            const name = (p.project_name || '').toLowerCase();
            const type = (p.type || '').toLowerCase();
            const date = (p.created_at || '').toLowerCase();
            return name.includes(q) || type.includes(q) || date.includes(q);
        });

        const isGlobalMatch = !q || 'dự án dùng chung'.includes(q) || 'shared'.includes(q) || 'global'.includes(q);

        // 3. Tính toán phân trang chuẩn xác theo projectsPageSize
        const totalPrivate = filteredPrivate.length;
        const totalPages = Math.max(1, Math.ceil(totalPrivate / projectsPageSize));

        if (currentProjectsPage > totalPages) currentProjectsPage = totalPages;
        if (currentProjectsPage < 1) currentProjectsPage = 1;

        const startIndex = (currentProjectsPage - 1) * projectsPageSize;
        const endIndex = Math.min(startIndex + projectsPageSize, totalPrivate);
        const pageItems = filteredPrivate.slice(startIndex, endIndex);

        // 4. Render Section 1: DỰ ÁN DÙNG CHUNG
        if (isGlobalMatch) {
            const trHeaderGlobal = document.createElement('tr');
            trHeaderGlobal.className = 'proj-group-header';
            trHeaderGlobal.style.background = '#f0fdf4';
            trHeaderGlobal.style.borderTop = '1px solid #bbf7d0';
            trHeaderGlobal.style.borderBottom = '1px solid #bbf7d0';
            trHeaderGlobal.innerHTML = `
                <td colspan="3" style="padding: 9px 18px; font-size: 11px; font-weight: 800; color: #166534; text-transform: uppercase; letter-spacing: 0.6px; white-space: nowrap;">
                    <i class="fa-solid fa-globe" style="margin-right:6px;"></i> DỰ ÁN DÙNG CHUNG
                </td>
            `;
            tbody.appendChild(trHeaderGlobal);

            const globalDateStr = globalProj.created_at ? globalProj.created_at.substring(0, 10) : '—';
            const trGlobal = document.createElement('tr');
            trGlobal.className = `proj-row-selectable ${isGlobalActive ? 'active-proj' : ''}`;
            trGlobal.style.background = isGlobalActive ? '#e6f4ea' : '#fcfdfd';
            trGlobal.innerHTML = `
                <td style="padding: 12px 18px; color: #64748b; font-size: 12px; white-space: nowrap; width: 140px;">${globalDateStr}</td>
                <td style="padding: 12px 18px; color: #00684a; font-weight: 700; white-space: nowrap;">
                    <div style="display: flex; align-items: center; gap: 8px; white-space: nowrap;">
                        <span>🌐 ${globalProj.project_name}</span>
                    </div>
                </td>
                <td style="padding: 12px 18px; color: #00684a; font-weight: 700; text-transform: uppercase; font-size: 11.5px; text-align: right; white-space: nowrap; width: 110px;">SHARED</td>
            `;
            trGlobal.onclick = () => {
                setActiveProjectName(globalProj.project_name, globalProj.project_id);
                closeSelectProjectModal();
                showToast(`Đã chọn: "${globalProj.project_name}"`, 'success');
                window.dispatchEvent(new CustomEvent('aip-project-changed', { detail: { ...globalProj } }));
            };
            tbody.appendChild(trGlobal);
        }

        // 5. Render Section 2: DỰ ÁN RIÊNG THEO WORKSPACE (Áp dụng phân trang pageItems)
        if (totalPrivate > 0 || !q) {
            const trHeaderPrivate = document.createElement('tr');
            trHeaderPrivate.className = 'proj-group-header';
            trHeaderPrivate.style.background = '#f8fafc';
            trHeaderPrivate.style.borderTop = '1px solid #e2e8f0';
            trHeaderPrivate.style.borderBottom = '1px solid #e2e8f0';
            trHeaderPrivate.innerHTML = `
                <td colspan="3" style="padding: 9px 18px; font-size: 11px; font-weight: 800; color: #475569; text-transform: uppercase; letter-spacing: 0.6px; white-space: nowrap;">
                    <i class="fa-solid fa-folder-tree" style="margin-right:6px;"></i> DỰ ÁN RIÊNG THEO WORKSPACE
                </td>
            `;
            tbody.appendChild(trHeaderPrivate);

            if (totalPrivate === 0) {
                const trEmpty = document.createElement('tr');
                trEmpty.innerHTML = `<td colspan="3" style="text-align:center; padding: 18px; color: #94a3b8; font-size: 12.5px; white-space: nowrap;">Chưa có dự án riêng nào. Bấm "+ DỰ ÁN MỚI" để tạo dự án riêng!</td>`;
                tbody.appendChild(trEmpty);
            } else {
                pageItems.forEach(p => {
                    const dateStr = p.created_at ? (p.created_at.includes('T') ? p.created_at.split('T')[0] : p.created_at.substring(0, 10)) : '—';
                    const typeStr = p.type || 'prepaid';
                    const isActive = (p.project_name === activeName && !isGlobalActive);

                    const tr = document.createElement('tr');
                    tr.className = `proj-row-selectable ${isActive ? 'active-proj' : ''}`;
                    tr.innerHTML = `
                        <td style="padding: 12px 18px; color: #334155; white-space: nowrap; width: 140px;">${dateStr}</td>
                        <td style="padding: 12px 18px; color: #001e2b; font-weight: 700; white-space: nowrap;">
                            <div style="display: flex; align-items: center; gap: 8px; white-space: nowrap;">
                                <span>📁 ${p.project_name}</span>
                            </div>
                        </td>
                        <td style="padding: 12px 18px; color: #001e2b; font-weight: 700; text-transform: uppercase; font-size: 11.5px; text-align: right; white-space: nowrap; width: 110px;">${typeStr}</td>
                    `;
                    tr.onclick = () => {
                        const pid = p.project_id || p.id || p.tenant_id;
                        setActiveProjectName(p.project_name, pid);
                        closeSelectProjectModal();
                        showToast(`Đã chọn dự án riêng: "${p.project_name}"`, 'success');
                        window.dispatchEvent(new CustomEvent('aip-project-changed', { detail: { ...p, project_id: pid } }));
                    };
                    tbody.appendChild(tr);
                });
            }
        }

        // 6. Cập nhật nhãn phân trang và trạng thái nút chuyển trang
        const countLabel = document.getElementById('proj-count-label');
        if (countLabel) {
            if (totalPrivate === 0) {
                countLabel.innerText = '0 of 0 riêng';
            } else {
                countLabel.innerText = `${startIndex + 1}-${endIndex} of ${totalPrivate} riêng`;
            }
        }

        const pageSizeSelect = document.getElementById('proj-page-size-select');
        if (pageSizeSelect) pageSizeSelect.value = projectsPageSize.toString();

        const prevBtn = document.getElementById('proj-prev-btn');
        const nextBtn = document.getElementById('proj-next-btn');

        if (prevBtn) {
            const canPrev = currentProjectsPage > 1;
            prevBtn.disabled = !canPrev;
            prevBtn.style.opacity = canPrev ? '1' : '0.25';
            prevBtn.style.cursor = canPrev ? 'pointer' : 'not-allowed';
            prevBtn.style.color = canPrev ? '#001e2b' : '#94a3b8';
        }

        if (nextBtn) {
            const canNext = currentProjectsPage < totalPages;
            nextBtn.disabled = !canNext;
            nextBtn.style.opacity = canNext ? '1' : '0.25';
            nextBtn.style.cursor = canNext ? 'pointer' : 'not-allowed';
            nextBtn.style.color = canNext ? '#001e2b' : '#94a3b8';
        }
    }

    function nextProjectsPage() {
        const q = (currentProjectsFilter || '').trim().toLowerCase();
        const allPrivate = (cachedProjectsList || []).filter(p => p.project_id !== 'global' && p.type !== 'global');
        const filteredPrivate = allPrivate.filter(p => {
            if (!q) return true;
            return (p.project_name || '').toLowerCase().includes(q) || (p.type || '').toLowerCase().includes(q) || (p.created_at || '').includes(q);
        });
        const totalPages = Math.max(1, Math.ceil(filteredPrivate.length / projectsPageSize));
        if (currentProjectsPage < totalPages) {
            currentProjectsPage++;
            renderProjectsTablePage();
        }
    }

    function prevProjectsPage() {
        if (currentProjectsPage > 1) {
            currentProjectsPage--;
            renderProjectsTablePage();
        }
    }

    function changeProjectsPageSize(val) {
        projectsPageSize = parseInt(val, 10) || 5;
        currentProjectsPage = 1;
        renderProjectsTablePage();
    }

    function filterProjectsList() {
        currentProjectsFilter = (document.getElementById('project-search-input')?.value || '').trim();
        currentProjectsPage = 1;
        renderProjectsTablePage();
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

    // 5. Toast Notification System (Chuẩn Single-Slot Quản lý Vòng đời trên Topbar)
    let activeToastTimer = null;

    function showToast(msg, type = 'info') {
        let container = document.getElementById('toast-container');
        const header = document.querySelector('.top-header');
        const headerRight = header ? header.querySelector('.header-right') : null;

        if (!container) {
            container = document.createElement('div');
            container.id = 'toast-container';
            if (header && headerRight) {
                header.insertBefore(container, headerRight);
            } else if (header) {
                header.appendChild(container);
            } else {
                document.body.appendChild(container);
            }
        } else if (header && container.parentElement !== header) {
            if (headerRight) {
                header.insertBefore(container, headerRight);
            } else {
                header.appendChild(container);
            }
        }

        // 1. Hủy timer cũ ngay lập tức nếu đang có thông báo trước đó
        if (activeToastTimer) {
            clearTimeout(activeToastTimer);
            activeToastTimer = null;
        }

        // 2. Dọn sạch container - Đảm bảo vật lý duy nhất 1 thông báo hiển thị trên Topbar
        container.innerHTML = '';

        const toast = document.createElement('div');
        toast.style.cssText = 'min-width:180px; max-width:100%; height:34px; padding:6px 12px; border-radius:7px; color:#fff; font-size:12px; font-weight:600; display:flex; align-items:center; justify-content:space-between; gap:10px; box-shadow:0 4px 12px rgba(0,20,40,0.2); opacity:1; font-family:var(--font-body); z-index:100000; animation:aipToastSlideIn 0.22s cubic-bezier(0.16, 1, 0.3, 1); pointer-events:auto;';
        toast.style.background = type === 'success' ? '#10b981' : (type === 'error' ? '#ef4444' : (type === 'warning' ? '#f59e0b' : '#00a4b8'));
        
        toast.innerHTML = `<span style="overflow:hidden; text-overflow:ellipsis; white-space:nowrap; display:flex; align-items:center; gap:6px;"><i class="fa-solid ${type === 'success' ? 'fa-check' : (type === 'error' ? 'fa-triangle-exclamation' : 'fa-circle-info')}" style="font-size:11px;"></i> ${msg}</span><span style="cursor:pointer; margin-left:auto; font-size:16px; line-height:1; opacity:0.85; padding:2px;" title="Đóng">&times;</span>`;

        // 3. Nút đóng thủ công
        const closeBtn = toast.querySelector('span:last-child');
        if (closeBtn) {
            closeBtn.onclick = (e) => {
                e.stopPropagation();
                if (activeToastTimer) clearTimeout(activeToastTimer);
                toast.style.animation = 'aipToastFadeOut 0.15s ease forwards';
                setTimeout(() => toast.remove(), 150);
            };
        }

        // 4. Quản lý timer: Tự động đóng sau 3.5s, tạm dừng đếm ngược khi hover chuột
        const scheduleDismiss = () => {
            activeToastTimer = setTimeout(() => {
                toast.style.animation = 'aipToastFadeOut 0.2s ease forwards';
                setTimeout(() => {
                    if (toast.parentElement) toast.remove();
                }, 200);
            }, 3500);
        };

        toast.onmouseenter = () => {
            if (activeToastTimer) clearTimeout(activeToastTimer);
        };
        toast.onmouseleave = () => {
            scheduleDismiss();
        };

        container.appendChild(toast);
        scheduleDismiss();
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

    function ensureConsoleNavigationSection() {
        const sidebar = document.querySelector('.sidebar');
        if (!sidebar) return null;

        let consoleSection = Array.from(sidebar.querySelectorAll('.nav-section')).find(section =>
            section.querySelector('.section-title span')?.textContent
                ?.trim().toLowerCase().includes('console')
        );

        if (!consoleSection) {
            consoleSection = document.createElement('div');
            consoleSection.className = 'nav-section';
            sidebar.prepend(consoleSection);
        }

        if (!consoleSection.querySelector('.nav-list') || consoleSection.querySelectorAll('.nav-item').length < 3) {
            consoleSection.innerHTML = `
                <div class="section-title">
                    <span><i class="fa-solid fa-terminal" aria-hidden="true"></i> CONSOLE</span>
                    <i class="fa-solid fa-chevron-down toggle-icon" aria-hidden="true"></i>
                </div>
                <ul class="nav-list">
                    <li class="nav-item"><a href="/staff/dashboard"><i class="fa-solid fa-chart-pie" aria-hidden="true"></i> Dashboard</a></li>
                    <li class="nav-item"><a href="/staff/apis"><i class="fa-solid fa-cubes" aria-hidden="true"></i> APIs</a></li>
                    <li class="nav-item"><a href="/staff/keys"><i class="fa-solid fa-key" aria-hidden="true"></i> API Keys</a></li>
                    <li class="nav-item"><a href="/staff/report"><i class="fa-solid fa-chart-line" aria-hidden="true"></i> API report</a></li>
                </ul>
            `;
        }
        return consoleSection;
    }

    function ensureDirectLinksSection() {
        const sidebar = document.querySelector('.sidebar');
        if (!sidebar) return;

        let paymentLink = sidebar.querySelector('.nav-direct-link a[href*="payment"]')?.parentElement;
        let contactLink = sidebar.querySelector('.nav-direct-link a[href*="contact"]')?.parentElement;

        if (!paymentLink) {
            paymentLink = document.createElement('div');
            paymentLink.className = 'nav-direct-link';
            paymentLink.innerHTML = `<a href="/staff/payment"><i class="fa-solid fa-credit-card" aria-hidden="true"></i> PAYMENT HISTORY</a>`;
            sidebar.appendChild(paymentLink);
        }
        if (!contactLink) {
            contactLink = document.createElement('div');
            contactLink.className = 'nav-direct-link';
            contactLink.innerHTML = `<a href="/staff/contact"><i class="fa-solid fa-headset" aria-hidden="true"></i> CONTACT US</a>`;
            sidebar.appendChild(contactLink);
        }

        let profileLink = sidebar.querySelector('.nav-direct-link a[href*="profile"]')?.parentElement;
        if (!profileLink) {
            profileLink = document.createElement('div');
            profileLink.className = 'nav-direct-link';
            profileLink.innerHTML = `<a href="/profile"><i class="fa-solid fa-user-gear" aria-hidden="true"></i> USER PROFILE</a>`;
            sidebar.appendChild(profileLink);
        }
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
                <span><i class="fa-solid fa-layer-group" aria-hidden="true"></i> APPLICATIONS</span>
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
            .find(({ item }) => {
                const apiId = item[2].toLowerCase();
                if (path.endsWith(`/apis/${apiId}`)) return true;
                if (apiId === 'rag-chat-enterprise-kb' && (path.includes('service_rag') || path.includes('rag-chat'))) return true;
                if (apiId.includes('efb24a03') && path.includes('service_llm')) return true;
                if (apiId.includes('3a72d1f9') && path.includes('service_stt')) return true;
                if (apiId.includes('8b51ef94') && path.includes('service_tts')) return true;
                if (apiId.includes('c194a2b3') && path.includes('service_ocr_id')) return true;
                if (apiId.includes('d285b3c4') && path.includes('service_ocr_dl')) return true;
                if (apiId.includes('e396c4d5') && path.includes('service_ocr_passport')) return true;
                if (apiId.includes('f4a7d5e6') && path.includes('service_image')) return true;
                if (apiId.includes('a5b8e6f7') && path.includes('service_moderation')) return true;
                if (apiId.includes('b6c9f7a8') && path.includes('service_vision_facematch')) return true;
                if (apiId.includes('c7da08b9') && path.includes('service_vision_liveness')) return true;
                if (apiId.includes('d8eb19ca') && path.includes('service_nlp_embeddings')) return true;
                if (apiId.includes('fa0d3bec') && path.includes('service_nlp_summarization')) return true;
                if (apiId.includes('e9fc2adb') && path.includes('service_nlp_translation')) return true;
                return false;
            });
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
            toggle.title = 'Đóng/Mở thanh điều hướng (Menu)';
            toggle.addEventListener('click', () => {
                setSidebarCollapsed(!document.body.classList.contains('staff-sidebar-collapsed'));
            });
            headerLeft.insertBefore(toggle, brand);
        }
        setSidebarCollapsed(localStorage.getItem('aip_staff_sidebar_collapsed') === 'true');

        let projSelector = headerLeft?.querySelector('.project-selector');
        if (projSelector) {
            projSelector.onclick = openSelectProjectModal;
            if (!projSelector.querySelector('#current-project-label')) {
                const activeProject = getActiveProjectName();
                projSelector.innerHTML = `<i class="fa-solid fa-folder"></i> <span id="current-project-label">${activeProject}</span> <i class="fa-solid fa-chevron-down" style="font-size: 10px;"></i>`;
            }
        }

        let toastContainer = document.getElementById('toast-container');
        if (!toastContainer) {
            toastContainer = document.createElement('div');
            toastContainer.id = 'toast-container';
        }
        let headerRight = header.querySelector('.header-right');
        if (!headerRight) {
            headerRight = document.createElement('div');
            headerRight.className = 'header-right';
            header.appendChild(headerRight);
        }
        header.insertBefore(toastContainer, headerRight);

        // Standardize header-right with bilingual dropdown + user menu matching Image 3
        if (!headerRight.querySelector('#current-lang-text') || !headerRight.querySelector('.user-menu')) {
            const currentLang = localStorage.getItem('aip_lang') === 'vi' ? 'Tiếng Việt' : 'English';
            headerRight.innerHTML = `
                <div class="lang-dropdown-container" style="position:relative; cursor:pointer;" onclick="StaffLayout.toggleLangDropdown(event)">
                    <i class="fa-solid fa-globe"></i> <span id="current-lang-text">${currentLang}</span> <i class="fa-solid fa-chevron-down" style="font-size: 10px;"></i>
                    <div id="lang-dropdown-menu" style="display:none; position:absolute; top:42px; right:0; background:#fff; color:#101828; border-radius:10px; box-shadow:0 10px 25px rgba(0,0,0,0.1); border:1px solid #e4e7ec; width:145px; z-index:10000; overflow:hidden;">
                        <div style="padding:10px 14px; font-weight:500; font-size:13.5px; display:flex; align-items:center; gap:8px; cursor:pointer;" onclick="StaffLayout.setAppLanguage('en'); event.stopPropagation();">
                            🇬🇧 English
                        </div>
                        <div style="padding:10px 14px; font-weight:500; font-size:13.5px; display:flex; align-items:center; gap:8px; border-top:1px solid #f2f4f7; cursor:pointer;" onclick="StaffLayout.setAppLanguage('vi'); event.stopPropagation();">
                            🇻🇳 Tiếng Việt
                        </div>
                    </div>
                </div>
                <div class="user-menu" style="display:flex; align-items:center; gap:10px; font-weight:500; color:#344054; cursor:pointer;" onclick="window.location.href='/profile'" title="Xem và chỉnh sửa hồ sơ cá nhân">
                    <span class="user-avatar" id="header-avatar">NL</span>
                    <span id="header-username" style="font-weight:600; font-size:13.5px; color:#101828;">Nam Lê</span>
                    <i class="fa-solid fa-right-from-bracket" title="Logout" style="margin-left:6px; cursor:pointer; color:#98a2b3;" onclick="event.stopPropagation(); StaffLayout.logoutUser()"></i>
                </div>
            `;
        }
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
            if (select.dataset.dropup === 'true' || select.classList.contains('dropup')) {
                wrapper.classList.add('is-dropup');
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
            const positionOptions = () => {
                if (select.dataset.dropup === 'true' || select.classList.contains('dropup') || wrapper.classList.contains('dropup') || select.getAttribute('data-direction') === 'up') {
                    wrapper.classList.add('is-dropup');
                    return;
                }
                if (select.dataset.dropup === 'false') {
                    wrapper.classList.remove('is-dropup');
                    return;
                }

                const rect = trigger.getBoundingClientRect();
                const viewportHeight = window.innerHeight || document.documentElement.clientHeight;
                const spaceBelow = viewportHeight - rect.bottom;
                const spaceAbove = rect.top;

                const container = trigger.closest('.staff-modal-box, .staff-modal-body, .modal-content, .modal-card, [class*="modal"]');
                let containerSpaceBelow = spaceBelow;
                if (container) {
                    const cRect = container.getBoundingClientRect();
                    containerSpaceBelow = cRect.bottom - rect.bottom;
                }

                if (containerSpaceBelow < 190 || (spaceBelow < 220 && spaceAbove > spaceBelow)) {
                    wrapper.classList.add('is-dropup');
                } else {
                    wrapper.classList.remove('is-dropup');
                }
            };

            const open = () => {
                if (trigger.disabled) return;
                syncValue();
                activeIndex = Math.max(0, select.selectedIndex);
                renderOptions();
                positionOptions();
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
        const headerAvatar = document.getElementById('header-avatar') || document.querySelector('.user-menu .user-avatar');
        if (userSession) {
            try {
                const user = JSON.parse(userSession);
                if (headerUsername) headerUsername.innerText = user.full_name || 'Nam Lê';
                if (headerAvatar) {
                    if (user.avatar_img) {
                        headerAvatar.innerHTML = `<img src="${user.avatar_img}" style="width:100%;height:100%;border-radius:50%;object-fit:cover;" alt="Avatar">`;
                    } else if (user.full_name) {
                        const parts = user.full_name.trim().split(/\s+/);
                        const initials = parts.length >= 2 ? (parts[0][0] + parts[parts.length - 1][0]).toUpperCase() : parts[0].substring(0, 2).toUpperCase();
                        headerAvatar.innerText = initials;
                    }
                }
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

    // 9. Standard Topbar & Sidebar Markup (Unified Image 3 & Image 4 MatDash)
    function syncTopbarAndSidebar() {
        const path = window.location.pathname.toLowerCase();
        
        ensureConsoleNavigationSection();
        const isApplicationRoute = syncApplicationsNavigation(path);
        ensureDirectLinksSection();

        // 1. Update Project Label & Sync Tenant ID
        const activeProject = getActiveProjectName();
        const projLabel = document.getElementById('current-project-label') || document.getElementById('staff-active-project');
        if (projLabel) projLabel.innerText = activeProject;
        const breadcrumbProject = document.getElementById('breadcrumb-project-name');
        if (breadcrumbProject) breadcrumbProject.innerText = activeProject;
        const rawP = localStorage.getItem('aip_projects');
        if (rawP) {
            try {
                const list = JSON.parse(rawP);
                const found = list.find(p => (p.project_name || '').trim().toLowerCase() === (activeProject || '').trim().toLowerCase());
                if (found && (found.project_id || found.id)) {
                    const pid = found.project_id || found.id;
                    localStorage.setItem('aip_active_tenant_id', pid);
                    localStorage.setItem('aip_active_project_id', pid);
                }
            } catch (e) {}
        }

        const isLinkActive = (href) => {
            if (!href) return false;
            const normHref = href.toLowerCase().replace(/\.html$/, '').replace(/\/$/, '');
            const normPath = path.replace(/\.html$/, '').replace(/\/$/, '');
            if (normPath === normHref || normPath.endsWith(normHref)) return true;
            if ((normPath.includes('rag-chat-enterprise-kb') || normPath.includes('service_rag')) &&
                (normHref.includes('rag-chat-enterprise-kb') || normHref.includes('service_rag'))) {
                return true;
            }
            return false;
        };

        // 2. Synchronize active state with MatDash pill styling
        document.querySelectorAll('.sidebar .nav-item').forEach(item => {
            const link = item.querySelector('a');
            if (link && isLinkActive(link.getAttribute('href'))) {
                item.classList.add('active');
            } else {
                item.classList.remove('active');
            }
        });

        document.querySelectorAll('.sidebar .nav-direct-link').forEach(item => {
            const link = item.querySelector('a');
            if (link && isLinkActive(link.getAttribute('href'))) {
                item.classList.add('active');
            } else {
                item.classList.remove('active');
            }
        });

        // 3. Section Collapsibles
        document.querySelectorAll('.sidebar .section-title').forEach(header => {
            header.onclick = () => toggleNavSection(header);
            const navList = header.nextElementSibling;
            if (!navList) return;

            const savedState = sessionStorage.getItem(getNavSectionStateKey(header));
            const isApplicationsSection = header.querySelector('span')?.textContent
                ?.trim().toLowerCase().includes('applications');
            const isOpen = isApplicationRoute && isApplicationsSection
                ? true
                : (savedState !== null ? savedState === 'open' : true);

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
            } catch (err) {
                console.warn('Dynamic import of page script failed, falling back to script element execution:', err);
                try {
                    const fallbackScript = document.createElement('script');
                    fallbackScript.textContent = moduleSource;
                    document.body.appendChild(fallbackScript);
                } catch (fallbackErr) {
                    console.error('Fallback script execution failed:', fallbackErr);
                }
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
        nextProjectsPage,
        prevProjectsPage,
        changeProjectsPageSize,
        renderProjectsTablePage,
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
        setSidebarCollapsed,
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
    window.nextProjectsPage = nextProjectsPage;
    window.prevProjectsPage = prevProjectsPage;
    window.changeProjectsPageSize = changeProjectsPageSize;
    window.renderProjectsTablePage = renderProjectsTablePage;
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
    window.setSidebarCollapsed = setSidebarCollapsed;

    // Auto-init on DOMContentLoaded
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', StaffLayout.init);
    } else {
        StaffLayout.init();
    }
})();
