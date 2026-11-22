// The Python (FastAPI) backend owns every /api/* route except /api/health.
const API = process.env.FLOWFORGE_API_URL || `http://127.0.0.1:${process.env.FLOWFORGE_API_PORT || 8000}`;

/** @type {import('next').NextConfig} */
const nextConfig = {
  poweredByHeader: false,
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API}/api/:path*` }];
  },
};

export default nextConfig;
