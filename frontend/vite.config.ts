import path from "node:path"
import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    // import.meta.dirname, а не __dirname. Vite 8 читает конфиг родным
    // загрузчиком Node и на __dirname печатает предупреждение о будущем
    // configLoader: "native" при КАЖДОМ старте `npm run dev` — шум над
    // первой строкой вывода, который со временем перестают читать целиком.
    // В vitest.config.ts стоит то же самое.
    alias: { "@": path.resolve(import.meta.dirname, "./src") },
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
