const apiPort = process.env.API_PORT ?? "8000";
const webPort = process.env.WEB_PORT ?? "3000";

const checks = [
  { name: "api healthz", url: `http://127.0.0.1:${apiPort}/healthz`, expected: 200 },
  { name: "api readyz", url: `http://127.0.0.1:${apiPort}/readyz`, expected: 200 },
  { name: "web login", url: `http://127.0.0.1:${webPort}/login`, expected: 200 },
];

async function run() {
  let failures = 0;

  for (const check of checks) {
    try {
      const response = await fetch(check.url, { method: "GET" });
      if (response.status !== check.expected) {
        failures += 1;
        console.error(`[smoke] FAIL ${check.name}: expected ${check.expected}, got ${response.status}`);
      } else {
        console.log(`[smoke] PASS ${check.name}: ${response.status}`);
      }
    } catch (error) {
      failures += 1;
      const message = error instanceof Error ? error.message : String(error);
      console.error(`[smoke] FAIL ${check.name}: ${message}`);
    }
  }

  if (failures > 0) {
    console.error(`[smoke] ${failures} check(s) failed`);
    process.exit(1);
  }

  console.log("[smoke] all compose checks passed");
}

run();
