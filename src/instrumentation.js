// Starts the colocated Python API for single-container deployments.
// When FLOWFORGE_API_URL is set (for example, on Vercel), the API is external
// and this Next.js process must not attempt to spawn a local Python child process.
export async function register() {
  if (process.env.NEXT_RUNTIME !== "nodejs") return;
  if (process.env.FLOWFORGE_API_URL) return;
  const { startBackend } = await import("./lib/backend-supervisor.js");
  startBackend();
}
