import fs from 'fs';
import { resolve } from 'path';
import { defineConfig } from 'vite';

// Plugin to support extensionless URLs and path aliases
function cleanUrlsPlugin() {
  return {
    name: 'clean-urls-plugin',
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        if (!req.url) return next();
        const urlParts = req.url.split('?');
        const pathname = urlParts[0];
        const search = urlParts[1] ? `?${urlParts[1]}` : '';

        // Handle root or static asset requests with explicit extensions
        if (pathname === '/' || pathname.includes('.')) {
          return next();
        }

        // 1. Direct match: .${pathname}.html
        const directHtml = resolve(__dirname, `.${pathname}.html`);
        if (fs.existsSync(directHtml)) {
          req.url = `${pathname}.html${search}`;
          return next();
        }

        // 2. Hyphen to underscore normalization (e.g. /staff/service-stt -> /staff/service_stt.html)
        const underscorePath = pathname.replace(/-/g, '_');
        const underscoreHtml = resolve(__dirname, `.${underscorePath}.html`);
        if (fs.existsSync(underscoreHtml)) {
          req.url = `${underscorePath}.html${search}`;
          return next();
        }

        // 3. Enterprise FPT.AI-compliant dynamic project & API routing
        if (pathname.match(/^\/(?:staff\/)?project\/[^/]+\/apis\/[^/]+/)) {
          req.url = `/staff/service_detail.html${search}`;
          return next();
        }
        if (pathname.match(/^\/(?:staff\/)?project\/[^/]+\/apis\/?$/)) {
          req.url = `/staff/apis.html${search}`;
          return next();
        }
        if (pathname.match(/^\/(?:staff\/)?project\/[^/]+\/?$/) || pathname.match(/^\/(?:staff\/)?project\/[^/]+\/dashboard\/?$/)) {
          req.url = `/staff/dashboard.html${search}`;
          return next();
        }
        if (pathname.startsWith('/staff/service-') || pathname.startsWith('/staff/service_')) {
          req.url = `/staff/service_detail.html${search}`;
          return next();
        }

        // 4. Common path rewrites
        if (pathname === '/login') {
          req.url = `/auth/login.html${search}`;
          return next();
        }
        if (pathname === '/signup') {
          req.url = `/auth/signup.html${search}`;
          return next();
        }
        if (pathname === '/staff' || pathname === '/staff/') {
          req.url = `/staff/dashboard.html${search}`;
          return next();
        }
        if (pathname === '/admin' || pathname === '/admin/') {
          req.url = `/admin/dashboard.html${search}`;
          return next();
        }

        next();
      });
    },
  };
}

export default defineConfig(() => {
  const backendTarget = process.env.VITE_BACKEND_URL || 'http://localhost:8000';

  return {
    root: '.',
    plugins: [cleanUrlsPlugin()],
    resolve: {
      alias: [
        { find: '/static/assets', replacement: resolve(__dirname, 'public/assets') },
        { find: '/assets', replacement: resolve(__dirname, 'public/assets') },
      ],
    },
    server: {
      host: '0.0.0.0',
      port: 5173,
      cors: true,
      proxy: {
        // Reverse proxy all API calls and documentation directly to the FastAPI Gateway
        '/v1': {
          target: backendTarget,
          changeOrigin: true,
        },
        '/admin/v1': {
          target: backendTarget,
          changeOrigin: true,
        },
        '/docs': {
          target: backendTarget,
          changeOrigin: true,
        },
        '/openapi.json': {
          target: backendTarget,
          changeOrigin: true,
        },
        '/health': {
          target: backendTarget,
          changeOrigin: true,
        },
      },
    },
  build: {
    outDir: 'dist',
    rollupOptions: {
      input: {
        main: resolve(__dirname, 'index.html'),
        login: resolve(__dirname, 'auth/login.html'),
        signup: resolve(__dirname, 'auth/signup.html'),
        status: resolve(__dirname, 'status.html'),
        // Admin Pages
        admin_dashboard: resolve(__dirname, 'admin/dashboard.html'),
        admin_keys: resolve(__dirname, 'admin/keys.html'),
        admin_users: resolve(__dirname, 'admin/users.html'),
        admin_aliases: resolve(__dirname, 'admin/aliases.html'),
        admin_endpoints: resolve(__dirname, 'admin/endpoints.html'),
        admin_jobs: resolve(__dirname, 'admin/jobs.html'),
        admin_audit: resolve(__dirname, 'admin/audit.html'),
        admin_playground: resolve(__dirname, 'admin/playground.html'),
        admin_docs: resolve(__dirname, 'admin/docs.html'),
        admin_staff: resolve(__dirname, 'admin/staff.html'),
        // Staff Pages
        staff_dashboard: resolve(__dirname, 'staff/dashboard.html'),
        staff_apis: resolve(__dirname, 'staff/apis.html'),
        staff_keys: resolve(__dirname, 'staff/keys.html'),
        staff_report: resolve(__dirname, 'staff/report.html'),
        staff_payment: resolve(__dirname, 'staff/payment.html'),
        staff_contact: resolve(__dirname, 'staff/contact.html'),
        staff_portal: resolve(__dirname, 'staff/portal.html'),
        staff_service_detail: resolve(__dirname, 'staff/service_detail.html'),
        staff_service_llm: resolve(__dirname, 'staff/service_llm.html'),
        staff_service_stt: resolve(__dirname, 'staff/service_stt.html'),
        staff_service_tts: resolve(__dirname, 'staff/service_tts.html'),
        staff_service_image: resolve(__dirname, 'staff/service_image.html'),
        staff_service_moderation: resolve(__dirname, 'staff/service_moderation.html'),
        staff_service_ocr_id: resolve(__dirname, 'staff/service_ocr_id.html'),
        staff_service_ocr_dl: resolve(__dirname, 'staff/service_ocr_dl.html'),
        staff_service_ocr_passport: resolve(__dirname, 'staff/service_ocr_passport.html'),
        staff_service_nlp_embeddings: resolve(__dirname, 'staff/service_nlp_embeddings.html'),
        staff_service_nlp_translation: resolve(__dirname, 'staff/service_nlp_translation.html'),
        staff_service_nlp_summarization: resolve(__dirname, 'staff/service_nlp_summarization.html'),
        staff_service_vision_facematch: resolve(__dirname, 'staff/service_vision_facematch.html'),
        staff_service_vision_liveness: resolve(__dirname, 'staff/service_vision_liveness.html'),
      },
    },
  },
};
});
