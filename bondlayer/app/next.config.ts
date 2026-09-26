import type { NextConfig } from "next";

// The console is served as static files by the FastAPI merchant server, under
// /console, from the generated `out/` directory. No Node at the venue, no CDN,
// no network: every byte is on disk and every number on screen is fetched from
// the same origin's /onboard API at runtime.
const nextConfig: NextConfig = {
  output: "export",
  basePath: "/console",
  assetPrefix: "/console",
  trailingSlash: true,
  images: { unoptimized: true },
};

export default nextConfig;
