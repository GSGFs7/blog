import { check } from "k6";
import http from "k6/http";

const base = (__ENV.BASE_URL || "http://blog-django.blog.svc.cluster.local:8000").replace(
  /\/$/,
  "",
);
const targetPath = __ENV.TARGET_PATH || "";

function positiveInteger(name, fallback) {
  const value = Number(__ENV[name] || fallback);
  if (!Number.isInteger(value) || value < 1) {
    throw new Error(`${name} must be a positive integer`);
  }
  return value;
}

if (!/^https?:\/\//.test(base)) {
  throw new Error("BASE_URL must start with http:// or https://");
}
if (targetPath && (!targetPath.startsWith("/") || targetPath.startsWith("//"))) {
  throw new Error("TARGET_PATH must be a path beginning with a single /");
}

const peakRate = positiveInteger("PEAK_RATE", 100);
const preAllocatedVUs = positiveInteger("PRE_ALLOCATED_VUS", 50);
const maxVUs = positiveInteger("MAX_VUS", 200);
const rampUpSeconds = positiveInteger("RAMP_UP_SECONDS", 60);
const holdSeconds = positiveInteger("HOLD_SECONDS", 60);
const rampDownSeconds = positiveInteger("RAMP_DOWN_SECONDS", 10);
if (maxVUs < preAllocatedVUs) {
  throw new Error("MAX_VUS must be at least PRE_ALLOCATED_VUS");
}

const scenario = {
  executor: "ramping-arrival-rate",
  startRate: 1,
  timeUnit: "1s",
  preAllocatedVUs,
  maxVUs,
  gracefulStop: "15s",
  stages: [
    { duration: `${rampUpSeconds}s`, target: peakRate },
    { duration: `${holdSeconds}s`, target: peakRate },
    { duration: `${rampDownSeconds}s`, target: 0 },
  ],
};

export const options = {
  scenarios: { read: scenario },
  setupTimeout: "30s",
  thresholds: {
    "http_req_failed{scenario:read}": ["rate<0.01"],
    "http_req_duration{scenario:read}": ["p(95)<500", "p(99)<1000"],
    checks: ["rate>0.99"],
    dropped_iterations: ["count==0"],
  },
};

function get(path, name) {
  return http.get(`${base}${path}`, {
    redirects: 0,
    timeout: "10s",
    tags: { name },
  });
}

function json(response) {
  try {
    return response.json();
  } catch {
    return null;
  }
}

export function setup() {
  console.log(`stress peakRate=${peakRate} base=${base} target=${targetPath || "mixed-read"}`);
  if (targetPath) {
    if (get(targetPath, "preflight").status !== 200) {
      throw new Error("TARGET_PATH preflight did not return 200; check redirects and routing");
    }
    return {};
  }

  const response = get("/api/post?page=1&size=20", "preflight");
  const data = json(response);
  if (response.status !== 200 || !data || !Array.isArray(data.posts) || !data.posts.length) {
    throw new Error("Mixed reads require at least one published post and a working /api/post");
  }

  return { posts: data.posts.map((post) => ({ id: post.id, slug: post.slug })) };
}

export default function (data) {
  if (targetPath) {
    check(get(targetPath, "custom-read"), { "custom status 200": (r) => r.status === 200 });
    return;
  }

  const post = data.posts[Math.floor(Math.random() * data.posts.length)];
  const choice = Math.random();
  if (choice < 0.2) {
    const response = get(`/blog/${encodeURIComponent(post.slug)}`, "article-html");
    check(response, {
      "article status 200": (r) => r.status === 200,
      "article is HTML": (r) =>
        (r.headers["Content-Type"] || "").includes("text/html") && r.body.includes("<html"),
    });
  } else if (choice < 0.5) {
    const response = get("/api/post?page=1&size=10", "post-list");
    check(response, {
      "list status 200": (r) => r.status === 200,
      "list contains posts": (r) => Array.isArray(json(r)?.posts),
    });
  } else if (choice < 0.85) {
    const response = get(`/api/post/${post.id}`, "post-detail");
    check(response, {
      "detail status 200": (r) => r.status === 200,
      "detail matches post": (r) => json(r)?.id === post.id,
    });
  } else {
    const response = get(`/api/comment/post/${post.id}`, "post-comments");
    check(response, {
      "comments status 200": (r) => r.status === 200,
      "comments contains list": (r) => Array.isArray(json(r)?.comments),
    });
  }
}
