import createClient from "openapi-fetch"
import type { paths } from "./schema"

/**
 * Единственный способ сходить в API. Пути, параметры и форма ответа
 * проверяются компилятором по сгенерированной схеме: маршрут, которого нет,
 * не соберётся.
 */
export const api = createClient<paths>({
  baseUrl: "/",
  // Без этого кука сессии не уезжает с запросом, и всё, кроме входа,
  // отвечает 401 при формально успешном входе.
  credentials: "include",
})

/** Ошибка, разобранная из единого конверта бэкенда. */
export interface ApiError {
  message: string
  field?: string
}

export function toApiError(error: unknown): ApiError {
  if (
    typeof error === "object" &&
    error !== null &&
    "error" in error &&
    typeof (error as { error: unknown }).error === "string"
  ) {
    const envelope = error as { error: string; field?: string | null }
    return { message: envelope.error, field: envelope.field ?? undefined }
  }
  // Сюда попадает только то, что бэкенд не оформил конвертом: обрыв связи,
  // ответ прокси, падение до обработчиков.
  return { message: "Сервер недоступен" }
}
