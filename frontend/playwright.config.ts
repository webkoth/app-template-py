import { existsSync } from "node:fs"
import { defineConfig } from "@playwright/test"

const PORT = 8100

// Конфигурация Playwright — обвязка, а не приложение, и окружение она
// читает сама: тот же .env в корне, что и бэкенд. Без этого
// документированная команда `cd frontend && npx playwright test` работает
// только у того, кто заранее экспортировал DATABASE_URL_E2E в свою оболочку,
// а у всех остальных прогон падает при старте сервера на «DATABASE_URL
// должна начинаться с postgresql://» — про забытую переменную там нет ни
// слова. Проверено.
//
// Заданная снаружи переменная имеет приоритет: в CI обе базы приходят из
// окружения job, и .env там нет вовсе.
const ENV_FILE = new URL("../.env", import.meta.url)
if (!process.env.DATABASE_URL_E2E && existsSync(ENV_FILE)) {
  process.loadEnvFile(ENV_FILE)
}

const DATABASE_URL_E2E = process.env.DATABASE_URL_E2E
if (!DATABASE_URL_E2E) {
  // Запасного варианта нет намеренно, хотя написать `?? DATABASE_URL`
  // соблазнительно: подстановка рабочего адреса означала бы, что сценарии
  // создают и меняют данные в рабочей базе — молча и ровно тогда, когда
  // переменную забыли. Обвязка pytest отказывается работать по той же
  // причине и теми же словами.
  throw new Error(
    "DATABASE_URL_E2E не задан. Сквозные тесты создают и меняют данные и " +
      "поэтому идут только в отдельную базу — смотри .env.example."
  )
}

/**
 * E2e идут против собранного приложения, которое раздаёт сам бэкенд, — то
 * есть против того же, что уедет на контур. Прогон через dev-сервер Vite
 * проверял бы конфигурацию, которой в бою не существует.
 */
export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false,
  use: { baseURL: `http://127.0.0.1:${PORT}` },
  webServer: {
    // alembic перед uvicorn обязателен: база e2e отдельная и пустая, а
    // приложение при старте читает таблицу пользователей (заводит первую
    // учётную запись). Без миграций оно падает на старте, и падают все
    // сценарии разом — с сообщением про отсутствующую таблицу, а не про
    // отсутствующую подготовку базы. DATABASE_URL из env ниже перекрывает
    // .env, поэтому миграции лягут именно в e2e; проверено.
    command:
      `npm run build && cd ../backend && uv run alembic upgrade head && ` +
      `uv run uvicorn app.main:app --port ${PORT}`,
    url: `http://127.0.0.1:${PORT}/api/health`,
    reuseExistingServer: !process.env.CI,
    timeout: 180_000,
    env: {
      // Отдельная база: тесты создают и меняют данные, и делать это в
      // рабочей базе нельзя.
      DATABASE_URL: DATABASE_URL_E2E,
      APP_ENV: "local",
      APP_AUTH_SECRET: "e2e-secret-not-used-anywhere-real-000000",
      COOKIE_SECURE: "false",
    },
  },
})
