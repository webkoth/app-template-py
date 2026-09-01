import { describe, expect, it } from "vitest"
import { DEFAULT_THEME, SHARED_COLORS, THEMES } from "./themes"

const MODES = ["light", "dark"] as const
const RAMP_KEYS = [
  "background",
  "foreground",
  "card",
  "primary",
  "primaryForeground",
  "muted",
  "mutedForeground",
  "border",
  "ring",
] as const
const SHARED_COLOR_KEYS = [
  "destructive",
  "success",
  "successForeground",
  "warning",
  "warningForeground",
  "info",
  "infoForeground",
  "highlight",
  "highlightForeground",
  "rose",
] as const

// TODO прошло бы проверку на непустоту, но не является цветом: значение
// обязано быть функцией oklch(...), как и заявлено в комментариях модуля.
const COLOR_PATTERN = /^oklch\(/

describe("набор тем", () => {
  it("содержит пять тем с уникальными именами", () => {
    expect(THEMES).toHaveLength(5)
    const names = THEMES.map((t) => t.name)
    expect(new Set(names).size).toBe(names.length)
  })

  it("тема по умолчанию — синяя и она есть в наборе", () => {
    expect(DEFAULT_THEME).toBe("blue")
    expect(THEMES.some((t) => t.name === DEFAULT_THEME)).toBe(true)
  })

  // Пропущенное значение обнаружилось бы как невидимая кнопка на чужом
  // контуре, а не при сборке: тип защищает от опечатки в ключе, но не от
  // темы, добавленной копипастой с половиной полей.
  it("каждая тема задаёт все девять значений в обоих режимах", () => {
    for (const theme of THEMES) {
      for (const mode of MODES) {
        for (const key of RAMP_KEYS) {
          expect(theme[mode][key], `${theme.name}.${mode}.${key}`).toMatch(
            COLOR_PATTERN
          )
        }
      }
      expect(theme.radius, `${theme.name}.radius`).toMatch(/rem$/)
      expect(theme.label, `${theme.name}.label`).toMatch(/\S/)
    }
  })

  // Следующая задача разворачивает SHARED_COLORS в CSS-токены наравне с
  // ramp-значениями тем: пустое или нецветовое поле здесь так же невидимо
  // сломает кнопку на чужом контуре, как и в THEMES.
  it("общие цвета заданы во всех режимах", () => {
    for (const mode of MODES) {
      for (const key of SHARED_COLOR_KEYS) {
        expect(
          SHARED_COLORS[mode][key],
          `SHARED_COLORS.${mode}.${key}`
        ).toMatch(COLOR_PATTERN)
      }
    }
  })
})
