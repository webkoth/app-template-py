import { describe, expect, it } from "vitest"

import { toApiError } from "./client"

describe("toApiError", () => {
  it("разбирает конверт бэкенда", () => {
    expect(toApiError({ error: "Логин занят", field: "login" })).toEqual({
      message: "Логин занят",
      field: "login",
    })
  })

  it("отказ по размеру от nginx читается как размер, а не как мёртвый сервер", () => {
    // Проверено на контуре: тело крупнее лимита vhost получает 413 с
    // HTML-телом, до бэкенда запрос не доходит вовсе, и конверта в нём нет.
    // Без этой ветки человек читал бы «Сервер недоступен» и шёл проверять,
    // жив ли контур, хотя достаточно взять файл поменьше.
    const refusal = Object.assign(new Error("HTTP 413"), { status: 413 })
    expect(toApiError(refusal).message).toBe("Файл слишком большой для сервера")
  })

  it("всё прочее без конверта — недоступный сервер", () => {
    // Обрыв связи и ответ прокси действительно неотличимы от лежащего
    // бэкенда, и врать про причину тут нечем.
    const broken = Object.assign(new Error("HTTP 502"), { status: 502 })
    expect(toApiError(broken).message).toBe("Сервер недоступен")
    expect(toApiError(new TypeError("Failed to fetch")).message).toBe(
      "Сервер недоступен"
    )
  })
})
