// k6 smoke test — quick sanity check that the API responds.
// Thresholds here should be relaxed (we just want to detect outages).

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate } from 'k6/metrics';

const errorRate = new Rate('errors');

export const options = {
  vus: 10,            // 10 virtual users
  duration: '30s',    // for 30 seconds
  thresholds: {
    // 95% of requests must complete in under 1 second
    http_req_duration: ['p(95)<1000'],
    // Error rate must be below 1%
    errors: ['rate<0.01'],
    // All requests must succeed
    http_req_failed: ['rate<0.01'],
  },
};

const BASE_URL = __ENV.BASE_URL || 'https://staging.your-domain.com';

export default function () {
  // Hit the health endpoint
  const res = http.get(`${BASE_URL}/health`);
  const ok = check(res, {
    'status is 200': (r) => r.status === 200,
    'has status field': (r) => r.json('status') === 'ok',
  });
  errorRate.add(!ok);

  sleep(1);
}
