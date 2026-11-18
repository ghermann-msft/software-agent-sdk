import { spawn } from "node:child_process";

const provider = process.argv[2];
const providers = {
  codex: {
    command: process.env.ACP_CODEX_COMMAND ?? String.raw`C:\ACP\codex-acp.cmd`,
    args: [],
    shell: true,
  },
  copilot: {
    command:
      process.env.ACP_COPILOT_COMMAND ?? String.raw`C:\Copilot\copilot.exe`,
    args: ["--acp", "--stdio", "--no-auto-update"],
    shell: false,
  },
};

const config = providers[provider];
if (!config) {
  throw new Error(`Expected provider to be one of: ${Object.keys(providers)}`);
}

const child = spawn(config.command, config.args, {
  shell: config.shell,
  windowsHide: true,
  stdio: ["pipe", "pipe", "pipe"],
});
let stdout = "";
let stderr = "";
let settled = false;

const timeout = setTimeout(() => {
  fail(`ACP initialize timed out for ${provider}: ${stderr}`);
}, 90_000);

function finish() {
  if (!child.killed) {
    child.kill();
  }
  clearTimeout(timeout);
}

function fail(message) {
  if (settled) {
    return;
  }
  settled = true;
  finish();
  console.error(message);
  process.exitCode = 1;
}

child.stderr.setEncoding("utf8");
child.stderr.on("data", (chunk) => {
  stderr += chunk;
});

child.stdout.setEncoding("utf8");
child.stdout.on("data", (chunk) => {
  stdout += chunk;
  const lines = stdout.split(/\r?\n/);
  stdout = lines.pop() ?? "";

  for (const line of lines) {
    if (!line.startsWith("{")) {
      continue;
    }
    let response;
    try {
      response = JSON.parse(line);
    } catch {
      continue;
    }
    const agentInfo = response?.id === 1 ? response.result?.agentInfo : undefined;
    if (!agentInfo?.name) {
      continue;
    }

    settled = true;
    finish();
    console.log(
      `ACP initialize succeeded for ${provider}: ${agentInfo.name} ${agentInfo.version}`,
    );
    return;
  }
});

child.on("error", (error) => {
  fail(`ACP process failed to start for ${provider}: ${error.message}`);
});
child.on("exit", (code, signal) => {
  if (!settled) {
    fail(
      `ACP process exited before initialize for ${provider}: ` +
        `code=${code} signal=${signal} stderr=${stderr}`,
    );
  }
});

child.stdin.write(
  `${JSON.stringify({
    jsonrpc: "2.0",
    id: 1,
    method: "initialize",
    params: {
      protocolVersion: 1,
      clientCapabilities: {},
      clientInfo: {
        name: "openhands-windows-smoke",
        version: "1.0.0",
      },
    },
  })}\n`,
);
