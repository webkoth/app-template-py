import { queryOptions } from "@tanstack/react-query"
import { api, unwrap } from "@/api/client"
import type { components } from "@/api/schema"

/**
 * Формы берутся из схемы, а не переписываются от руки.
 *
 * Рукописная копия сходится с бэкендом ровно до первой правки там: поле
 * переименовали — клиент собирается, читает undefined и показывает пустоту.
 * Здесь же переименование становится ошибкой компиляции, а ради этого
 * генерация типов из OpenAPI и заведена. Проверено: переименование role в
 * схеме роняет сборку в двух местах.
 */
export type CurrentUser = components["schemas"]["CurrentUserResponse"]
export type Role = CurrentUser["role"]

const RANK: Role[] = ["viewer", "editor", "admin"]

/** Хватает ли роли, чтобы показать элемент интерфейса. */
export function hasRank(actual: Role, required: Role): boolean {
  return RANK.indexOf(actual) >= RANK.indexOf(required)
}

/**
 * Текущий пользователь. Это ЕДИНСТВЕННОЕ место, где клиент узнаёт о правах,
 * и служит оно только показу: спрятанная кнопка не защищает ничего.
 * Проверку делает каждый роутер на бэкенде через require_role.
 */
export const currentUserQuery = queryOptions({
  queryKey: ["auth", "me"],
  queryFn: async (): Promise<CurrentUser | null> => {
    const result = await api.GET("/api/auth/me")
    // 401 — это норма, а не сбой: человек ещё не вошёл. Бросив здесь, мы бы
    // показывали экран ошибки вместо формы входа.
    if (result.response.status === 401) return null
    // Всё остальное — через unwrap, как и любой другой вызов api. Раньше
    // здесь стояло `data ?? null`, и это был единственный вызов мимо
    // unwrap: 500, 502 и обрыв связи давали то же самое null, что и «не
    // вошёл», роутер уводил на форму входа, и лежащий бэкенд был
    // неотличим от незалогиненного человека. Владелец в этот момент
    // набирает верный пароль и получает молчание.
    return unwrap(result)
  },
  retry: false,
  staleTime: 30_000,
})
