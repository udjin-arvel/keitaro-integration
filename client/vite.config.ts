import { defineConfig } from "@lovable.dev/vite-tanstack-config";

export default defineConfig({
  tanstackStart: {
    server: { entry: "server" },
  },
  nitro: { preset: "node-server" },
  vite: {
    server: {
      allowedHosts: ["dev118.arvelov.space"],
    },
  },
});
