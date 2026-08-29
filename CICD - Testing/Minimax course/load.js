// k6 load test — heavier than smoke. Find the breaking point.

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Trend } from 'k6/metrics';

const chatLatency = new Trend('chat_latency');

export const options = {
  stages: [
    { duration: '30s', target: 20 },   // ramp up to 20 users over 30s
    { duration: '1m',  target: 50 },   // ramp to 50 users over 1m
    { duration: '30s', target: 100 },  // spike to 100 users
    { duration: '1m',  target: 50 },   // ramp back down
    { duration: '30s', target: 0 },    // cool down
  ],
  thresholds: {
    // 95th percentile latency < 2s for the chat endpoint
    'http_req_duration{endpoint:chat}': ['p(95)<2000'],
    // Custom metric: chat latency
    chat_latency: ['p(95)<3000'],
  },
};

const BASE_URL = __ENV.BASE_URL || 'https://staging.your-domain.com';

export default function () {
  const payload = JSON.stringify({
    message: 'Hello, what is FastAPI?',
  });
  const params = {
    headers: { 'Content-Type': 'application/json' },
    tags: { endpoint: 'chat' },
  };
  const start = Date.now();
  const res = http.post(`${BASE_URL}/api/chat`, payload, params);
  chatLatency.add(Date.now() - start);

  check(res, {
    'status is 200': (r) => r.status === 200,
    'has reply': (r) => r.json('reply') !== undefined,
  });

  sleep(1);
}
