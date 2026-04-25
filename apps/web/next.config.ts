import path from "node:path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  outputFileTracingRoot: path.resolve(__dirname, "../.."),
  typescript: {
    ignoreBuildErrors: true,
  },
};

export default nextConfig;
