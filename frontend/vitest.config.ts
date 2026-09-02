import path from "node:path"
import { defineConfig } from "vitest/config"

export default defineConfig({
  resolve: { alias: { "@": path.resolve(import.meta.dirname, "./src") } },
  test: {
    environment: "node",
    // Тесты только на чистую логику. Unit-тесты на React-компоненты
    // запрещены правилами проекта — их роль выполняет e2e.
    include: ["src/lib/**/*.test.ts"],
  },
})
