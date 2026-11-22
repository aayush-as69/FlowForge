export const dynamic = "force-dynamic";

async function pythonStatus() {
  const port = process.env.FLOWFORGE_API_PORT || 8000;
  try {
    const res = await fetch(`http://127.0.0.1:${port}/api/system/health`, { signal: AbortSignal.timeout(800) });
    return res.ok ? "up" : "degraded";
  } catch {
    return "starting";
  }
}

export async function GET() {
  const api = await pythonStatus();
  return Response.json({ ok: api === "up", api }, { status: api === "up" ? 200 : 503 });
}
