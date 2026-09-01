import path from "node:path"
import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  server: {
    port: 5173,
    // В разработке фронтенд и бэкенд живут на разных портах. Прокси делает
    // их одним источником для браузера: иначе кука сессии не уезжает с
    // запросом, и вход «работает», но следующий же вызов отвечает 401.
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: true },
    },
  },
  build: {
    // Сюда смотрит app/core/static.py.
    outDir: "dist",
  },
})
