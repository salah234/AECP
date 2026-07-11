import type { NextConfig } from "next";

// All API calls go to the Gateway (see lib/api-client.ts). The dashboard
// never holds a service credential or talks to internal gRPC services
// directly; NEXT_PUBLIC_GATEWAY_URL is the only backend origin it knows
// about.
const nextConfig: NextConfig = {
  reactStrictMode: true,
  output: "standalone",
};

export default nextConfig;
