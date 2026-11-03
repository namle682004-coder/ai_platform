import fs from 'fs';
import { resolve } from 'path';
import { defineConfig } from 'vite';

// Plugin to support extensionless URLs, new Solutions/Console routes, and legacy staff aliases
const UNFINISHED_API_IDS = new Set([
  'a5b8e6f7-9154-4c65-d816-e42705f43678', // Moderation
  'd8eb19ca-2487-4f98-0b49-175038c76901', // Embeddings
  'fa0d3bec-46a9-41ba-2d6b-39725ae98123', // Summarization
  'e9fc2adb-3598-40a9-1c5a-286149d87012', // Translation
  '8b51ef94-912a-4367-bf16-36701a09cb12', // TTS
  'f4a7d5e6-8043-4b54-c705-d31694e32567', // Image Gen
  'd285b3c4-6821-4932-a583-b19472c10345', // Driver License
  'e396c4d5-7932-4a43-b694-c20583d21456', // Passport
  'b6c9f7a8-0265-4d76-e927-f53816a54789', // FaceMatch
  'c7da08b9-1376-4e87-fa38-064927b65890', // Liveness
]);

const DEV_URL_MAPPING = {
  '/staff/service-moderation': 'a5b8e6f7-9154-4c65-d816-e42705f43678',
  '/staff/service_moderation': 'a5b8e6f7-9154-4c65-d816-e42705f43678',
  '/staff/service_moderation.html': 'a5b8e6f7-9154-4c65-d816-e42705f43678',
  '/playgrounds/moderation_raw': 'a5b8e6f7-9154-4c65-d816-e42705f43678',
  '/playgrounds/moderation_raw.html': 'a5b8e6f7-9154-4c65-d816-e42705f43678',

  '/staff/service-tts': '8b51ef94-912a-4367-bf16-36701a09cb12',
  '/staff/service_tts': '8b51ef94-912a-4367-bf16-36701a09cb12',
  '/staff/service_tts.html': '8b51ef94-912a-4367-bf16-36701a09cb12',
  '/solutions/voice/tts_synthesis': '8b51ef94-912a-4367-bf16-36701a09cb12',
  '/solutions/voice/tts_synthesis.html': '8b51ef94-912a-4367-bf16-36701a09cb12',

  '/staff/service-image': 'f4a7d5e6-8043-4b54-c705-d31694e32567',
  '/staff/service_image': 'f4a7d5e6-8043-4b54-c705-d31694e32567',
  '/staff/service_image.html': 'f4a7d5e6-8043-4b54-c705-d31694e32567',
  '/playgrounds/image_gen_raw': 'f4a7d5e6-8043-4b54-c705-d31694e32567',
  '/playgrounds/image_gen_raw.html': 'f4a7d5e6-8043-4b54-c705-d31694e32567',

  '/staff/service-ocr-dl': 'd285b3c4-6821-4932-a583-b19472c10345',
  '/staff/service_ocr_dl': 'd285b3c4-6821-4932-a583-b19472c10345',
  '/staff/service_ocr_dl.html': 'd285b3c4-6821-4932-a583-b19472c10345',
  '/solutions/ekyc/drivers_license': 'd285b3c4-6821-4932-a583-b19472c10345',
  '/solutions/ekyc/drivers_license.html': 'd285b3c4-6821-4932-a583-b19472c10345',

  '/staff/service-ocr-passport': 'e396c4d5-7932-4a43-b694-c20583d21456',
  '/staff/service_ocr_passport': 'e396c4d5-7932-4a43-b694-c20583d21456',
  '/staff/service_ocr_passport.html': 'e396c4d5-7932-4a43-b694-c20583d21456',
  '/solutions/ekyc/passport': 'e396c4d5-7932-4a43-b694-c20583d21456',
  '/solutions/ekyc/passport.html': 'e396c4d5-7932-4a43-b694-c20583d21456',

  '/staff/service-vision-facematch': 'b6c9f7a8-0265-4d76-e927-f53816a54789',
  '/staff/service_vision_facematch': 'b6c9f7a8-0265-4d76-e927-f53816a54789',
  '/staff/service_vision_facematch.html': 'b6c9f7a8-0265-4d76-e927-f53816a54789',
  '/solutions/ekyc/facematch': 'b6c9f7a8-0265-4d76-e927-f53816a54789',
  '/solutions/ekyc/facematch.html': 'b6c9f7a8-0265-4d76-e927-f53816a54789',

  '/staff/service-vision-liveness': 'c7da08b9-1376-4e87-fa38-064927b65890',
  '/staff/service_vision_liveness': 'c7da08b9-1376-4e87-fa38-064927b65890',
  '/staff/service_vision_liveness.html': 'c7da08b9-1376-4e87-fa38-064927b65890',
  '/solutions/ekyc/liveness': 'c7da08b9-1376-4e87-fa38-064927b65890',
  '/solutions/ekyc/liveness.html': 'c7da08b9-1376-4e87-fa38-064927b65890',

  '/staff/service-nlp-embeddings': 'd8eb19ca-2487-4f98-0b49-175038c76901',
  '/staff/service_nlp_embeddings': 'd8eb19ca-2487-4f98-0b49-175038c76901',
  '/staff/service_nlp_embeddings.html': 'd8eb19ca-2487-4f98-0b49-175038c76901',
  '/playgrounds/embeddings_raw': 'd8eb19ca-2487-4f98-0b49-175038c76901',
  '/playgrounds/embeddings_raw.html': 'd8eb19ca-2487-4f98-0b49-175038c76901',

  '/staff/service-nlp-summarization': 'fa0d3bec-46a9-41ba-2d6b-39725ae98123',
  '/staff/service_nlp_summarization': 'fa0d3bec-46a9-41ba-2d6b-39725ae98123',
  '/staff/service_nlp_summarization.html': 'fa0d3bec-46a9-41ba-2d6b-39725ae98123',

  '/staff/service-nlp-translation': 'e9fc2adb-3598-40a9-1c5a-286149d87012',
  '/staff/service_nlp_translation': 'e9fc2adb-3598-40a9-1c5a-286149d87012',
  '/staff/service_nlp_translation.html': 'e9fc2adb-3598-40a9-1c5a-286149d87012',
  '/playgrounds/translation_raw': 'e9fc2adb-3598-40a9-1c5a-286149d87012',
  '/playgrounds/translation_raw.html': 'e9fc2adb-3598-40a9-1c5a-286149d87012',
};

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
          if (UNFINISHED_API_IDS.has(apiId)) {
            req.url = `/shared/under_development.html?service=${apiId}${search ? '&' + search.slice(1) : ''}`;
            return next();
          }
          const page = apiRouteConfig.apiPages[apiId];
          if (page) {
            req.url = `/staff/${page}${search}`;
            return next();
          }
        }

        // Dedicated Under Development route
        if (pathname === '/under-development' || pathname === '/under_development' || pathname === '/staff/under-development' || pathname === '/console/under-development') {
          req.url = `/shared/under_development.html${search}`;
          return next();
        }

        // Unfinished / In-development services intercepted and routed to under-development notice
        if (DEV_URL_MAPPING[pathname]) {
          const serviceId = DEV_URL_MAPPING[pathname];
          req.url = `/shared/under_development.html?service=${serviceId}${search ? '&' + search.slice(1) : ''}`;
          return next();
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
          under_development: resolve(__dirname, 'shared/under_development.html'),
        },
      },
    },
  };
});
