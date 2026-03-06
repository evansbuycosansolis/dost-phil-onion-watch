import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  transpilePackages: [
    "@phil-onion-watch/types",
    "@phil-onion-watch/domain",
    "@phil-onion-watch/config",
    "@phil-onion-watch/api-client",
    "@phil-onion-watch/ui",
    "@phil-onion-watch/ai-prompts",
  ],
};

export default nextConfig;
