import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Native addon — must not be bundled / Edge-routed.
  serverExternalPackages: ["better-sqlite3"],
};

export default nextConfig;
