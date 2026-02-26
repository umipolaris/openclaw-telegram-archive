const internalApiBase = (process.env.INTERNAL_API_BASE ?? "http://api:8000/api").replace(/\/$/, "");

/** @type {import('next').NextConfig} */
const nextConfig = {
  experimental: {
    typedRoutes: true,
  },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${internalApiBase}/:path*`,
      },
    ];
  },
};

export default nextConfig;
