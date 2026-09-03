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
    // Код ответа кладётся на подставной Error: без него отказ, пришедший
    // НЕ в конверте бэкенда, неотличим от обрыва связи — а отличать их надо
    // (см. toApiError про 413).
    const status = result.response.status
    const fallback = new Error(`HTTP ${status}`)
    Object.assign(fallback, { status })
    throw result.error ?? fallback
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
  // Отказ по размеру от nginx, а не от приложения. Проверено на контуре:
  // тело крупнее лимита vhost получает 413 с HTML-телом, до бэкенда запрос
  // не доходит вовсе, и конверта в нём нет — а без этой ветки человек
  // читает «Сервер недоступен» и идёт проверять, жив ли контур, хотя
  // достаточно взять файл поменьше.
  //
  // Предел здесь НЕ называется числом намеренно: у приложения он свой
  // (UPLOAD_MAX_BYTES), у vhost свой, и они не обязаны совпадать — вписав
  // сюда одно из них, мы бы врали ровно в тот момент, когда сработало
  // другое.
  if (
    typeof error === "object" &&
    error !== null &&
    (error as { status?: unknown }).status === 413
  ) {
    return { message: "Файл слишком большой для сервера" }
  }
  // Сюда попадает только то, что бэкенд не оформил конвертом: обрыв связи,
  // ответ прокси, падение до обработчиков.
  return { message: "Сервер недоступен" }
}
