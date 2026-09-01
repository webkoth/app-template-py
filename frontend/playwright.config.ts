import { defineConfig } from "@playwright/test"

const PORT = 8100

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
      DATABASE_URL:
        process.env.DATABASE_URL_E2E ?? process.env.DATABASE_URL ?? "",
      APP_ENV: "local",
      APP_AUTH_SECRET: "e2e-secret-not-used-anywhere-real-000000",
      COOKIE_SECURE: "false",
    },
  },
})
