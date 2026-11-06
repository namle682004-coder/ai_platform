/*
 * Project console URLs (same scheme as the gateway and vite, see shared/api_detail_routes.json):
 *
 *   /projects/{project}                              project dashboard
 *   /projects/{project}/services                     service catalog
 *   /projects/{project}/services/{service}/{view…}   a service page; {view…} is a view of that page,
 *                                                    e.g. rag-chatbot/chat/{session_id}, rag-chatbot/knowledge/qa
 *   /services/{service}/{view…}                      the same page in the current project (rewritten here)
 *
 * {project} is the project's slug ("shared" for the shared knowledge scope, internally tenant "global").
 * The URL is the source of truth: on load the project it names becomes the active one before any page
 * script reads it, switching project rewrites the URL, and a link opens the project it names (or says
 * the viewer has no such project). localStorage only remembers the last project for links without one.
 *
 * Loaded as a classic script in <head>, before the page's own scripts.
 */
(function (window) {
    'use strict';
    if (window.AipRoutes) return; // loaded both from <head> and by staff_layout.js

    // Former ids (endpoint UUIDs) of each service: links and the catalog still carry them.
    // Kept in step with shared/api_detail_routes.json (checked by tests/test_console_routes.py).
    const SERVICES = {
        'rag-chatbot': 'rag-chat-enterprise-kb',
        'llm-chat': 'efb24a03-059d-440c-bd35-0b5b3a776983',
        'speech-to-text': '3a72d1f9-46c8-472e-8395-cb091a136701',
        'text-to-speech': '8b51ef94-912a-4367-bf16-36701a09cb12',
        'ocr-cccd': 'c194a2b3-5710-4821-9472-a08361b09234',
        'ocr-driver-license': 'd285b3c4-6821-4932-a583-b19472c10345',
        'ocr-passport': 'e396c4d5-7932-4a43-b694-c20583d21456',
        'image-generation': 'f4a7d5e6-8043-4b54-c705-d31694e32567',
        'moderation': 'a5b8e6f7-9154-4c65-d816-e42705f43678',
        'face-match': 'b6c9f7a8-0265-4d76-e927-f53816a54789',
        'liveness': 'c7da08b9-1376-4e87-fa38-064927b65890',
        'embeddings': 'd8eb19ca-2487-4f98-0b49-175038c76901',
        'summarization': 'fa0d3bec-46a9-41ba-2d6b-39725ae98123',
        'translation': 'e9fc2adb-3598-40a9-1c5a-286149d87012',
    };
    const LIVE_SERVICES = new Set(['rag-chatbot', 'llm-chat', 'speech-to-text', 'ocr-cccd']);

    const SHARED_PROJECT = { project_id: 'global', project_name: 'Dự án Dùng Chung', type: 'global', slug: 'shared' };
    const RESERVED_SLUGS = new Set(['shared', 'global', 'new', 'current', 'settings', 'projects', 'services',
        'dashboard', 'keys', 'usage', 'billing', 'admin', 'api', 'v1']);
    const MAX_SLUG_LENGTH = 48;

    // ------------------------------------------------------------------ projects
    function slugify(name) {
        const ascii = String(name || '').replace(/đ/g, 'd').replace(/Đ/g, 'D')
            .normalize('NFKD').replace(/[^\x00-\x7f]/g, '');
        const slug = ascii.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '')
            .slice(0, MAX_SLUG_LENGTH).replace(/-+$/g, '');
        return slug || 'project';
    }

    function projectId(project) {
        return project ? String(project.project_id || project.id || project.tenant_id || '') : '';
    }

    function withSlugs(list) {
        // Same derivation as the gateway (api/project_slugs.py) for lists cached before slugs existed.
        const taken = new Set(RESERVED_SLUGS);
        list.forEach(p => { if (p.slug) taken.add(p.slug); });
        list.filter(p => !p.slug)
            .sort((a, b) => (String(a.created_at || '') + projectId(a)).localeCompare(String(b.created_at || '') + projectId(b)))
            .forEach(p => {
                const base = slugify(p.project_name);
                let candidate = base;
                for (let n = 2; taken.has(candidate); n += 1) candidate = `${base}-${n}`;
                taken.add(candidate);
                p.slug = candidate;
            });
        return list;
    }

    function projects() {
        try {
            const list = JSON.parse(localStorage.getItem('aip_projects') || '[]');
            return Array.isArray(list) ? withSlugs(list.filter(p => projectId(p) !== SHARED_PROJECT.project_id)) : [];
        } catch (e) {
            return [];
        }
    }

    function slugOf(project) {
        if (!project) return null;
        if (projectId(project) === SHARED_PROJECT.project_id || project.type === 'global') return SHARED_PROJECT.slug;
        if (project.slug) return project.slug;
        const listed = projects().find(p => projectId(p) === projectId(project));
        return listed ? listed.slug : slugify(project.project_name);
    }

    function findProject(segment) {
        if (!segment) return null;
        const key = safeDecode(segment).toLowerCase();
        if (key === SHARED_PROJECT.slug || key === SHARED_PROJECT.project_id) return SHARED_PROJECT;
        const list = projects();
        return list.find(p => p.slug === key) || list.find(p => projectId(p).toLowerCase() === key) || null;
    }

    function activeProject() {
        let id = null, name = null;
        try {
            id = localStorage.getItem('aip_active_project_id');
            name = localStorage.getItem('aip_active_project');
        } catch (e) { /* storage unavailable: no remembered project */ }
        if (id === SHARED_PROJECT.project_id) return SHARED_PROJECT;
        const list = projects();
        return list.find(p => projectId(p) === id) || list.find(p => p.project_name === name) || list[0] || null;
    }

    function activate(project) {
        try {
            localStorage.setItem('aip_active_project', project.project_name);
            localStorage.setItem('aip_active_project_id', projectId(project));
            localStorage.setItem('aip_active_tenant_id', projectId(project));
        } catch (e) { /* storage unavailable: the URL still names the project */ }
    }

    // ------------------------------------------------------------------ services
    function serviceSlug(idOrSlug) {
        const key = String(idOrSlug || '').toLowerCase().trim();
        if (SERVICES[key]) return key;
        const found = Object.entries(SERVICES).find(([, legacy]) => legacy.toLowerCase() === key);
        return found ? found[0] : null;
    }

    // ------------------------------------------------------------------ URLs
    function safeDecode(value) {
        try { return decodeURIComponent(value); } catch (e) { return value; }
    }

    function parse(pathname) {
        const parts = String(pathname || '').split('/').filter(Boolean).map(safeDecode);
        if (parts[0] === 'projects') {
            const route = { project: parts[1] || null, section: 'dashboard', service: null, view: [] };
            if (parts[2] === 'services') {
                route.section = parts[3] ? 'service' : 'services';
                route.service = parts[3] || null;
                route.view = parts.slice(4);
            } else if (parts[2] && parts[2] !== 'dashboard') {
                route.section = parts[2];
                route.view = parts.slice(3);
            }
            return route;
        }
        if (parts[0] === 'services' && parts[1]) {
            return { project: null, section: 'service', service: parts[1], view: parts.slice(2) };
        }
        return null;
    }

    function build(route, projectSlug) {
        let path = `/projects/${encodeURIComponent(projectSlug)}`;
        const view = (route.view || []).filter(Boolean).map(encodeURIComponent);
        if (route.section === 'services') path += '/services';
        else if (route.section === 'service') path += `/services/${encodeURIComponent(route.service)}`;
        else if (route.section && route.section !== 'dashboard') path += `/${encodeURIComponent(route.section)}`;
        return view.length && route.section !== 'services' && route.section !== 'dashboard' ? `${path}/${view.join('/')}` : path;
    }

    function samePage(a, b) {
        return !!a && !!b && a.section === b.section && serviceSlug(a.service) === serviceSlug(b.service) &&
            (a.project || '').toLowerCase() === (b.project || '').toLowerCase();
    }

    function currentProjectSlug() {
        const route = parse(window.location.pathname);
        if (route && route.project) return route.project;
        const project = activeProject();
        return project ? slugOf(project) : SHARED_PROJECT.slug;
    }

    function replaceUrl(path) {
        const next = path + window.location.search + window.location.hash;
        if (next !== window.location.pathname + window.location.search + window.location.hash) {
            window.history.replaceState(window.history.state, '', next);
        }
    }

    function notify(message) {
        const show = () => window.StaffLayout && typeof window.StaffLayout.showToast === 'function'
            ? (window.StaffLayout.showToast(message, 'error'), true) : false;
        if (!show()) window.addEventListener('DOMContentLoaded', () => setTimeout(show, 300), { once: true });
    }

    // ------------------------------------------------------------------ lifecycle
    let pageRoute = null; // the page this document shows; deeper segments are its views

    /** The project named by the URL becomes the active one; the URL is rewritten to its canonical form. */
    function syncFromUrl() {
        const route = parse(window.location.pathname);
        pageRoute = route;
        if (!route) return null;
        if (route.section === 'service') route.service = serviceSlug(route.service) || route.service;
        const named = route.project ? findProject(route.project) : null;
        if (named) activate(named);
        if (route.project && !named) return route; // unknown here yet: checked once the project list arrives
        const project = named || activeProject();
        if (project) {
            route.project = slugOf(project);
            replaceUrl(build(route, route.project));
        }
        return route;
    }

    /** Called with the viewer's projects as returned by the gateway (they carry their slugs). */
    function onProjects(list) {
        if (Array.isArray(list)) {
            try { localStorage.setItem('aip_projects', JSON.stringify(list)); } catch (e) { /* cache only */ }
        }
        const route = parse(window.location.pathname);
        if (!route) return;
        if (!route.project) {
            syncFromUrl();
            return;
        }
        const named = findProject(route.project);
        if (named) {
            const switched = projectId(named) !== (localStorage.getItem('aip_active_project_id') || '');
            activate(named);
            if (switched) {
                // The page drew the previously active project before the list arrived: draw the right one.
                window.location.reload();
                return;
            }
            syncFromUrl();
            return;
        }
        const fallback = activeProject();
        notify(`Không tìm thấy dự án "${route.project}" hoặc bạn không có quyền truy cập. Đang hiển thị dự án hiện tại.`);
        if (fallback) {
            pageRoute = { ...route, project: slugOf(fallback), view: [] };
            replaceUrl(build(pageRoute, pageRoute.project));
        }
    }

    window.addEventListener('aip-project-changed', (event) => {
        const route = parse(window.location.pathname);
        if (!route) return;
        const detail = (event && event.detail) || {};
        const id = String(detail.project_id || detail.id || detail.tenant_id || '');
        const project = id === SHARED_PROJECT.project_id ? SHARED_PROJECT
            : projects().find(p => projectId(p) === id) || detail;
        const slug = slugOf(project);
        if (!slug) return;
        // Views (a conversation, a document) belong to the previous project: the new one opens on the page itself.
        pageRoute = { ...route, project: slug, view: [] };
        const next = build(pageRoute, slug);
        if (next !== window.location.pathname) window.history.pushState({ aipView: true }, '', next);
    });

    /** Shows a view of the current page in the URL (pushed to history unless `replace`). */
    function setView(segments, options) {
        const route = parse(window.location.pathname);
        if (!route || route.section !== 'service') return;
        const next = build({ ...route, view: (segments || []).filter(Boolean) }, route.project || currentProjectSlug());
        if (next === window.location.pathname) return;
        const method = options && options.replace ? 'replaceState' : 'pushState';
        window.history[method]({ aipView: true }, '', next + window.location.search);
    }

    function currentView() {
        const route = parse(window.location.pathname);
        return route && route.section === 'service' ? route.view : [];
    }

    /** True when `url` shows the same page as this document (only the view differs): no page load needed. */
    function isSamePage(url) {
        return samePage(parse(url.pathname), pageRoute);
    }

    function serviceHref(idOrSlug, view) {
        const slug = serviceSlug(idOrSlug) || String(idOrSlug || '');
        return build({ section: 'service', service: slug, view: view || [] }, currentProjectSlug());
    }

    function currentServiceLegacyId() {
        const route = parse(window.location.pathname);
        const slug = route && route.section === 'service' ? serviceSlug(route.service) : null;
        return slug ? SERVICES[slug] : null;
    }

    window.AipRoutes = {
        SERVICES, LIVE_SERVICES, SHARED_PROJECT,
        slugify, slugOf, projectId, findProject, activeProject, serviceSlug,
        parse, build, syncFromUrl, onProjects, setView, currentView, isSamePage,
        serviceHref, currentServiceLegacyId, currentProjectSlug,
        isServiceLive: (idOrSlug) => LIVE_SERVICES.has(serviceSlug(idOrSlug) || ''),
        servicesHref: () => build({ section: 'services' }, currentProjectSlug()),
        dashboardHref: () => build({ section: 'dashboard' }, currentProjectSlug()),
    };

    syncFromUrl();
})(window);
