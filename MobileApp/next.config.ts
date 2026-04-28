import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Static export so the same build deploys to Vercel, GitHub Pages, S3, etc.
  // The PWA hits the FastAPI backend at NEXT_PUBLIC_BACKEND_BASE_URL for
  // both REST (artworks) and WebSocket (voice). No server-side Next code.
  output: "export",
  images: { unoptimized: true },
};

export default nextConfig;
