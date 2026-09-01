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

/**
 * Данные ответа или исключение. Через это проходит КАЖДЫЙ вызов api:
 * queryFn должна бросать, иначе react-query считает запрос удавшимся, а
 * mutationFn — иначе onSuccess отработает на неслучившемся изменении.
 *
 * Проверяется код ответа, а не наличие разобранного тела. Привычное
 * `if (error) throw error` пропускает отказ с пустым или не-JSON телом:
 * openapi-fetch кладёт в error только то, что разобрал. Воспроизведено с
 * остановленным бэкендом — прокси Vite отвечает «502 Bad Gateway,
 * text/plain, ноль байт», error оказывается пустым, и форма «Новый расход»
 * очищалась, будто расход сохранён. Молчаливый ложный успех хуже
 * молчаливого отказа: человек уходит уверенным, что данные записаны.
 */
export function unwrap<T>(result: {
  data?: T
  error?: unknown
  response: Response
}): T {
  if (!result.response.ok) {
    // error как есть: конверт бэкенда разберёт toApiError. Пустое тело —
    // подставной Error, чтобы бросаемое значение никогда не было undefined:
    // react-query такой отказ показал бы как успех с пустыми данными.
    throw result.error ?? new Error(`HTTP ${result.response.status}`)
  }
  return result.data as T
}

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
