import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { setTimeout as delay } from "node:timers/promises";

const port = 18_000 + Math.floor(Math.random() * 10_000);
const baseUrl = `http://127.0.0.1:${port}`;
const testPassword = "local-ci-password-only";
let logs = "";
let processExited = false;

const server = spawn(process.execPath, [".next/standalone/server.js"], {
  cwd: process.cwd(),
  env: {
    ...process.env,
    NODE_ENV: "production",
    PORT: String(port),
    HOSTNAME: "127.0.0.1",
    PANEL_ACCESS_PASSWORD: testPassword,
    PANEL_SESSION_SECRET: "local-ci-session-secret-only",
    OLIMPO_API_URL: "http://127.0.0.1:9",
    OLIMPO_API_TOKEN: "",
  },
  stdio: ["ignore", "pipe", "pipe"],
});

server.stdout.on("data", (chunk) => { logs += chunk.toString(); });
server.stderr.on("data", (chunk) => { logs += chunk.toString(); });
server.on("exit", () => { processExited = true; });

async function stopServer() {
  if (processExited) return;
  server.kill();
  await Promise.race([
    new Promise((resolve) => server.once("exit", resolve)),
    delay(5_000),
  ]);
}

try {
  let ready = false;
  for (let attempt = 0; attempt < 40; attempt += 1) {
    if (processExited) throw new Error(`Painel saiu antes de iniciar.\n${logs}`);
    try {
      const response = await fetch(`${baseUrl}/login`, { redirect: "manual" });
      if (response.status === 200) {
        ready = true;
        break;
      }
    } catch {
      // O servidor ainda está subindo.
    }
    await delay(250);
  }
  assert.ok(ready, `Painel não iniciou a tempo.\n${logs}`);

  const wrongPassword = await fetch(`${baseUrl}/api/login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ password: "wrong-password" }),
  });
  assert.equal(wrongPassword.status, 401, "senha incorreta precisa ser recusada");

  const withoutSession = await fetch(baseUrl, { redirect: "manual" });
  assert.equal(withoutSession.status, 307, "página privada deve redirecionar ao login");
  assert.match(withoutSession.headers.get("location") ?? "", /\/login$/);

  const privateApiWithoutSession = await fetch(`${baseUrl}/api/olimpo/v1/overview`);
  assert.equal(privateApiWithoutSession.status, 401, "proxy precisa exigir sessão");

  const login = await fetch(`${baseUrl}/api/login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ password: testPassword }),
  });
  assert.equal(login.status, 200, "senha correta deve iniciar sessão");

  const setCookie = login.headers.get("set-cookie") ?? "";
  assert.match(setCookie, /HttpOnly/i);
  assert.match(setCookie, /Secure/i);
  assert.match(setCookie, /SameSite=Strict/i);
  const sessionCookie = setCookie.match(/olimpo_session=[^;]+/)?.[0];
  assert.ok(sessionCookie, "resposta de login precisa definir cookie de sessão");

  const privatePageWithSession = await fetch(baseUrl, {
    headers: { cookie: sessionCookie },
    redirect: "manual",
  });
  assert.equal(privatePageWithSession.status, 200, "sessão válida deve abrir o painel");

  console.log("Smoke de autenticação de produção passou.");
} finally {
  await stopServer();
}

