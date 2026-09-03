import path from "node:path"
import { defineConfig } from "vitest/config"

export default defineConfig({
  resolve: { alias: { "@": path.resolve(import.meta.dirname, "./src") } },
  test: {
    environment: "node",
    // Тесты только на чистую логику. Unit-тесты на React-компоненты
    // запрещены правилами проекта — их роль выполняет e2e.
    //
    // Запрет держится РАСШИРЕНИЕМ, а не каталогом: компоненты живут в .tsx,
    // и шаблон `.test.ts` их не подберёт при всём желании. Каталогом это
    // держалось хуже: `src/lib/**` молча не запускал ничего за пределами
    // lib, и файл с проверками разбора ошибок API просто не собирался —
    // vitest говорил «No test files found» только при прямом запуске, а в
    // `make check` этого не видно вовсе.
    include: ["src/**/*.test.ts"],
  },
})
