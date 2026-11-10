/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: false, // map + Deck overlay mount once, deliberately
  transpilePackages: ["@deck.gl/core", "@deck.gl/layers", "@deck.gl/mapbox", "@luma.gl/core", "@luma.gl/engine", "@loaders.gl/core"],
};
export default nextConfig;
