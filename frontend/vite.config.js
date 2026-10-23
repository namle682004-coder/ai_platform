import fs from 'fs';
import { resolve } from 'path';
import { defineConfig } from 'vite';

// Plugin to support extensionless URLs, new Solutions/Console routes, and legacy staff aliases
function cleanUrlsPlugin() {
  const routesFile = fs.existsSync(resolve(__dirname, 'shared/api_detail_routes.json'))
    ? resolve(__dirname, 'shared/api_detail_routes.json')
    : resolve(__dirname, 'staff/api_detail_routes.json');

  const apiRouteConfig = JSON.parse(fs.readFileSync(routesFile, 'utf8'));

  return {
    name: 'clean-urls-plugin',
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        if (!req.url) return next();
        const urlParts = req.url.split('?');
        const pathname = urlParts[0];
        const search = urlParts[1] ? `?${urlParts[1]}` : '';

        // Dynamic project API routing: /project/:id/apis/:apiId
        const projectApiMatch = pathname.match(/^\/(?:staff\/)?project\/[^/]+\/apis\/([^/]+)\/?$/i);
        if (projectApiMatch) {
          const apiId = projectApiMatch[1].toLowerCase();
          if (apiId.includes('rag') || apiId === 'rag-chat-enterprise-kb') {
            req.url = `/solutions/rag/index.html${search}`;
            return next();
          }
          const page = apiRouteConfig.apiPages[apiId];
          if (page) {
            req.url = `/staff/${page}${search}`;
            return next();
          }
        }

        // Direct match
        const directHtml = resolve(__dirname, `.${pathname}.html`);
        if (fs.existsSync(directHtml)) {
          req.url = `${pathname}.html${search}`;
          return next();
        }

        // Short-cut clean URLs:
        if (pathname === '/login') { req.url = `/auth/login.html${search}`; return next(); }
        if (pathname === '/signup') { req.url = `/auth/signup.html${search}`; return next(); }
        if (pathname === '/rag' || pathname === '/chat') { req.url = `/solutions/rag/index.html${search}`; return next(); }
        if (pathname === '/dashboard') { req.url = `/console/dashboard.html${search}`; return next(); }
        if (pathname === '/keys') { req.url = `/console/keys.html${search}`; return next(); }
        if (pathname === '/payment') { req.url = `/console/payment.html${search}`; return next(); }
        if (pathname === '/report') { req.url = `/console/report.html${search}`; return next(); }
        if (pathname === '/profile' || pathname === '/staff/profile') { req.url = `/console/profile.html${search}`; return next(); }

        // Dynamic project dashboard: /project/:id/dashboard
        if (pathname.match(/^\/(?:staff\/)?project\/[^/]+(?:\/dashboard)?\/?$/)) {
          req.url = `/console/dashboard.html${search}`;
          return next();
        }

        // Legacy /staff rewrites
        if (pathname === '/staff' || pathname === '/staff/') {
          req.url = `/console/dashboard.html${search}`;
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
        { find: '/shared', replacement: resolve(__dirname, 'shared') },
      ],
    },
    server: {
      host: '0.0.0.0',
      port: 5173,
      cors: true,
      proxy: {
        '/v1': { target: backendTarget, changeOrigin: true },
        '/admin/v1': { target: backendTarget, changeOrigin: true },
        '/docs': { target: backendTarget, changeOrigin: true },
        '/openapi.json': { target: backendTarget, changeOrigin: true },
        '/health': { target: backendTarget, changeOrigin: true },
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
          // Admin
          admin_dashboard: resolve(__dirname, 'admin/dashboard.html'),
          admin_keys: resolve(__dirname, 'admin/keys.html'),
          admin_users: resolve(__dirname, 'admin/users.html'),
          // Console
          console_dashboard: resolve(__dirname, 'console/dashboard.html'),
          console_apis: resolve(__dirname, 'console/apis.html'),
          console_keys: resolve(__dirname, 'console/keys.html'),
          console_report: resolve(__dirname, 'console/report.html'),
          console_payment: resolve(__dirname, 'console/payment.html'),
          console_profile: resolve(__dirname, 'console/profile.html'),
          // Solutions
          solution_rag: resolve(__dirname, 'solutions/rag/index.html'),
          solution_cccd: resolve(__dirname, 'solutions/ekyc/id_card_cccd.html'),
          solution_stt: resolve(__dirname, 'solutions/voice/stt_transcription.html'),
          solution_tts: resolve(__dirname, 'solutions/voice/tts_synthesis.html'),
          // Playgrounds
          play_llm: resolve(__dirname, 'playgrounds/llm_raw.html'),
          play_image: resolve(__dirname, 'playgrounds/image_gen_raw.html'),
        },
      },
    },
  };
});
