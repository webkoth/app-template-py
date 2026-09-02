/**
 * Показ денег и дат. Единственное место, откуда форматируют и таблица, и
 * подпись на графике.
 *
 * Разбор пользовательского ввода живёт на бэкенде: он решает, что попадёт
 * в базу, и обязан быть авторитетным. Здесь только показ.
 */

const MONEY = new Intl.NumberFormat("ru-RU", {
  style: "currency",
  currency: "RUB",
  minimumFractionDigits: 2,
})

const DATE = new Intl.DateTimeFormat("ru-RU", {
  timeZone: "Europe/Moscow",
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
})

const DATE_TIME = new Intl.DateTimeFormat("ru-RU", {
  timeZone: "Europe/Moscow",
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
})

/** Копейки — в строку для человека. Делитель ровно 100, без округлений. */
export function formatMoney(minor: number): string {
  return MONEY.format(minor / 100)
}

export function formatDate(iso: string): string {
  return DATE.format(new Date(iso))
}

export function formatDateTime(iso: string): string {
  return DATE_TIME.format(new Date(iso))
}
