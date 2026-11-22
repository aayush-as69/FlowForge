// Starts (and supervises) the Python backend alongside the Next.js server.
export async function register() {
  if (process.env.NEXT_RUNTIME !== "nodejs") return;
  const { startBackend } = await import("./lib/backend-supervisor.js");
  startBackend();
}
