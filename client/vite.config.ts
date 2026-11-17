import { defineConfig } from "@lovable.dev/vite-tanstack-config";

export default defineConfig({
  tanstackStart: {
    server: { entry: "server" },
  },
  nitro: { preset: "node-server" },
  vite: {
    server: {
      allowedHosts: ["dev118.arvelov.space"],
      proxy: {
        "/api": {
          target: process.env.API_PROXY_TARGET || "http://127.0.0.1:8000",
          changeOrigin: true,
        },
      },
    },
  },
});
