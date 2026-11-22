import { spawn, spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

export function startBackend() {
  if (globalThis.__flowforgeBackend) return;
  globalThis.__flowforgeBackend = true;

  const backendDir = path.join(/*turbopackIgnore: true*/ process.cwd(), "backend");
  const libs = path.join(backendDir, ".pylibs");
  const python = process.env.PYTHON_BIN || "python3";

  if (!fs.existsSync(/*turbopackIgnore: true*/ path.join(libs, "fastapi"))) {
    console.log("[flowforge] installing Python dependencies…");
    spawnSync(/*turbopackIgnore: true*/ python, ["-m", "pip", "install", "--quiet", "--target", libs, "-r", "requirements.txt"], {
      cwd: backendDir,
      stdio: "inherit",
    });
  }

  let crashes = 0;
  const launch = () => {
    const started = Date.now();
    const child = spawn(/*turbopackIgnore: true*/ python, ["run.py"], { cwd: backendDir, stdio: "inherit", env: process.env });
    globalThis.__flowforgeChild = child;
    child.on("exit", (code) => {
      if (Date.now() - started < 5000) crashes += 1;
      else crashes = 0;
      if (crashes >= 5) {
        console.error("[flowforge] Python backend keeps crashing; giving up. Check backend logs above.");
        return;
      }
      console.error(`[flowforge] Python backend exited (${code}); restarting…`);
      setTimeout(launch, 1500);
    });
  };
  launch();

  const stop = () => globalThis.__flowforgeChild?.kill("SIGTERM");
  process.on("exit", stop);
  process.on("SIGTERM", () => {
    stop();
    process.exit(0);
  });
}
