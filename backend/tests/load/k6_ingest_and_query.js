import http from 'k6/http';
import { check, sleep } from 'k6';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
const API_BASE = `${BASE_URL}/api`;
const ADMIN_USER = __ENV.ADMIN_USER || 'admin';
const ADMIN_PASSWORD = __ENV.ADMIN_PASSWORD || 'ChangeMe123!';
const SAMPLE_FILE = open('./fixtures/sample.txt', 'b');

export const options = {
  scenarios: {
    query: {
      executor: 'ramping-vus',
      startVUs: 1,
      stages: [
        { duration: '30s', target: 10 },
        { duration: '1m', target: 20 },
        { duration: '30s', target: 0 },
      ],
      exec: 'queryScenario',
    },
    ingest: {
      executor: 'constant-arrival-rate',
      rate: 2,
      timeUnit: '1s',
      duration: '2m',
      preAllocatedVUs: 4,
      maxVUs: 10,
      exec: 'ingestScenario',
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.05'],
    http_req_duration: ['p(95)<2000'],
  },
};

function loginAndBuildCookie() {
  const payload = JSON.stringify({ username: ADMIN_USER, password: ADMIN_PASSWORD });
  const res = http.post(`${API_BASE}/auth/login`, payload, {
    headers: { 'Content-Type': 'application/json' },
  });
  check(res, { 'login status 200': (r) => r.status === 200 });

  const cookie = res.cookies?.archive_session?.[0]?.value;
  if (!cookie) {
    throw new Error('archive_session cookie not found');
  }
  return `archive_session=${cookie}`;
}

export function setup() {
  return {
    cookieHeader: loginAndBuildCookie(),
  };
}

function authHeaders(cookieHeader) {
  return {
    Cookie: cookieHeader,
  };
}

export function queryScenario(data) {
  const headers = authHeaders(data.cookieHeader);
  const listRes = http.get(`${API_BASE}/documents?page=1&size=100&sort_by=event_date&sort_order=desc`, { headers });
  check(listRes, { 'documents list 200': (r) => r.status === 200 });

  const searchRes = http.get(`${API_BASE}/documents?page=1&size=100&q=테스트&sort_by=ingested_at&sort_order=desc`, {
    headers,
  });
  check(searchRes, { 'documents search 200': (r) => r.status === 200 });
  sleep(1);
}

export function ingestScenario(data) {
  const headers = authHeaders(data.cookieHeader);
  const sourceRef = `load:${Date.now()}:${__VU}:${__ITER}`;
  const formData = {
    source: 'manual',
    source_ref: sourceRef,
    title: `k6-load-${__VU}-${__ITER}`,
    description: 'k6 load ingest',
    caption: `k6 load ingest\n#분류:부하테스트\n#날짜:2026-02-24\n#태그:load,k6`,
    file: http.file(SAMPLE_FILE, `k6-${__VU}-${__ITER}.txt`, 'text/plain'),
  };
  const ingestRes = http.post(`${API_BASE}/ingest/manual`, formData, { headers });
  check(ingestRes, { 'manual ingest accepted': (r) => r.status === 202 });
}
