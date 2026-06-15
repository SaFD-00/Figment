import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Konva's module entry pulls in `index-node.js`, which `require("canvas")`
  // (a server-only native module we don't ship). `ssr: false` stops rendering
  // but not bundling, so webpack still tries to resolve `canvas` and fails.
  // Alias it to an empty module — the browser path never touches it.
  webpack: (config) => {
    config.resolve.alias = {
      ...config.resolve.alias,
      canvas: false,
    };
    return config;
  },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: "http://127.0.0.1:8000/:path*",
      },
    ];
  },
};

export default nextConfig;
