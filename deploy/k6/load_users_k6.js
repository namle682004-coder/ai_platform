import http from 'k6/http';
import { check, sleep } from 'k6';

// Kubernetes Load Test - Type 1: High User Concurrency & RPS
// Targets AIP Control Plane Gateway behind Kubernetes Ingress
export const options = {
  stages: [
    { duration: '30s', target: 50 },   // Warm-up to 50 concurrent users
    { duration: '1m',  target: 200 },  // Ramp-up to 200 concurrent users
    { duration: '2m',  target: 500 },  // Sustained load at 500 concurrent users
    { duration: '30s', target: 1000 }, // Peak spike test at 1,000 users
    { duration: '30s', target: 0 },    // Cool-down
  ],
  thresholds: {
    // 95% of requests must complete below 250ms under peak load
    http_req_duration: ['p(95)<250', 'p(99)<600'],
    // Network failure rate must stay below 1%
    http_req_failed: ['rate<0.01'],
  },
};

const BASE_URL = __ENV.TARGET_URL || 'http://localhost:8000';
const API_KEY = __ENV.API_KEY || 'aip_live_loadtestkey123';

export default function () {
  const params = {
    headers: {
      'Authorization': `Bearer ${API_KEY}`,
      'Content-Type': 'application/json',
      'X-Request-Source': 'k6-load-test',
    },
    timeout: '5s',
  };

  // 1. Health Probe Verification
  const healthRes = http.get(`${BASE_URL}/health/live`, params);
  check(healthRes, {
    'health status is 200': (r) => r.status === 200,
  });

  // 2. Project API Catalog & Metadata Navigation
  const catalogRes = http.get(`${BASE_URL}/project/f40b6a70-ea64-4d01-90dc-53a2d7a81395/apis`, params);
  check(catalogRes, {
    'catalog status is 200': (r) => r.status === 200,
  });

  // Brief pause simulating realistic human think time between clicks
  sleep(0.05);
}
