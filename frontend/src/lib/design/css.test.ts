import { describe, expect, it } from "vitest"
import { buildThemeCss } from "./css"
import {
  SHARED_COLORS,
  THEMES,
  findTheme,
  type Ramp,
  type SharedColors,
  type Theme,
} from "./themes"

/**
 * Сорок имён из :root файла app/globals.css на момент внедрения тем.
 * Список записан здесь литералом намеренно: сверять сгенерированное с
 * самим генератором бессмысленно, проверка обязана держаться за то, чего
 * ждёт разметка.
 */
const ROOT_TOKENS = [
  "--background",
  "--foreground",
  "--card",
  "--card-foreground",
  "--popover",
  "--popover-foreground",
  "--primary",
  "--primary-foreground",
  "--secondary",
  "--secondary-foreground",
  "--muted",
  "--muted-foreground",
  "--accent",
  "--accent-foreground",
  "--destructive",
  "--success",
  "--success-foreground",
  "--warning",
  "--warning-foreground",
  "--info",
  "--info-foreground",
  "--highlight",
  "--highlight-foreground",
  "--border",
  "--input",
  "--ring",
  "--chart-1",
  "--chart-2",
  "--chart-3",
  "--chart-4",
  "--chart-5",
  "--radius",
  "--sidebar",
  "--sidebar-foreground",
  "--sidebar-primary",
  "--sidebar-primary-foreground",
  "--sidebar-accent",
  "--sidebar-accent-foreground",
  "--sidebar-border",
  "--sidebar-ring",
]

function block(css: string, selector: string): string {
  const start = css.indexOf(`${selector} {`)
  expect(start, `блок ${selector} не найден`).toBeGreaterThanOrEqual(0)
  return css.slice(start, css.indexOf("}", start))
}

/**
 * Разбирает блок объявлений (текст между `{` и `}`) в словарь «токен →
 * значение». Один парсер на оба теста ниже: дублировать regex в двух
 * местах — значит однажды поправить его только в одном.
 */
function parseDeclarations(blockCss: string): Record<string, string> {
  const result: Record<string, string> = {}
  for (const line of blockCss.split("\n")) {
    const match = /^\s*(--[\w-]+):\s*(.+);\s*$/.exec(line)
    if (match) {
      result[match[1]] = match[2]
    }
  }
  return result
}

/**
 * Тема-эталон: девять значений режима различны между собой, а тёмные не
 * совпадают со светлыми.
 *
 * На настоящих темах так не выходит. У синей, например, light.background и
 * light.card оба равны oklch(1 0 0) — перестановка именно этой пары в
 * declarations() не изменила бы результат, и таблица ниже её пропустила бы.
 * Совпадение значений маскирует ошибку отображения; синтетические значения
 * маскировку снимают, и тогда любая перестановка меняет вывод.
 */
const SENTINEL: Theme = {
  name: "sentinel",
  label: "Эталон",
  radius: "0.321rem",
  light: {
    background: "oklch(0.101 0 0)",
    foreground: "oklch(0.102 0 0)",
    card: "oklch(0.103 0 0)",
    primary: "oklch(0.104 0 0)",
    primaryForeground: "oklch(0.105 0 0)",
    muted: "oklch(0.106 0 0)",
    mutedForeground: "oklch(0.107 0 0)",
    border: "oklch(0.108 0 0)",
    ring: "oklch(0.109 0 0)",
  },
  dark: {
    background: "oklch(0.201 0 0)",
    foreground: "oklch(0.202 0 0)",
    card: "oklch(0.203 0 0)",
    primary: "oklch(0.204 0 0)",
    primaryForeground: "oklch(0.205 0 0)",
    muted: "oklch(0.206 0 0)",
    mutedForeground: "oklch(0.207 0 0)",
    border: "oklch(0.208 0 0)",
    ring: "oklch(0.209 0 0)",
  },
}

/**
 * Контракт отображения, записанный руками: какой токен из какого значения
 * берётся. Это независимое от css.ts утверждение — параметром сюда приходит
 * только режим, а сама раскладка написана по спеке и живёт здесь одна на
 * оба блока.
 *
 * Радиуса тут нет: он не зависит от режима и добавляется к :root отдельно.
 */
function expectedDeclarations(
  ramp: Ramp,
  shared: SharedColors,
): Record<string, string> {
  return {
    "--background": ramp.background,
    "--foreground": ramp.foreground,
    "--card": ramp.card,
    "--card-foreground": ramp.foreground,
    "--popover": ramp.card,
    "--popover-foreground": ramp.foreground,
    "--primary": ramp.primary,
    "--primary-foreground": ramp.primaryForeground,
    "--secondary": ramp.muted,
    "--secondary-foreground": ramp.foreground,
    "--muted": ramp.muted,
    "--muted-foreground": ramp.mutedForeground,
    "--accent": ramp.muted,
    "--accent-foreground": ramp.foreground,
    "--destructive": shared.destructive,
    "--success": shared.success,
    "--success-foreground": shared.successForeground,
    "--warning": shared.warning,
    "--warning-foreground": shared.warningForeground,
    "--info": shared.info,
    "--info-foreground": shared.infoForeground,
    "--highlight": shared.highlight,
    "--highlight-foreground": shared.highlightForeground,
    "--border": ramp.border,
    "--input": ramp.border,
    "--ring": ramp.ring,
    "--chart-1": ramp.primary,
    "--chart-2": shared.highlight,
    "--chart-3": shared.info,
    "--chart-4": shared.warning,
    "--chart-5": shared.rose,
    "--sidebar": ramp.card,
    "--sidebar-foreground": ramp.foreground,
    "--sidebar-primary": ramp.primary,
    "--sidebar-primary-foreground": ramp.primaryForeground,
    "--sidebar-accent": ramp.muted,
    "--sidebar-accent-foreground": ramp.foreground,
    "--sidebar-border": ramp.border,
    "--sidebar-ring": ramp.ring,
  }
}

describe("buildThemeCss", () => {
  const blue = findTheme("blue")!

  it("отдаёт оба блока", () => {
    const css = buildThemeCss(blue)
    expect(css).toContain(":root {")
    expect(css).toContain(".dark {")
  })

  it("в :root объявлены все сорок токенов", () => {
    const root = block(buildThemeCss(blue), ":root")
    for (const token of ROOT_TOKENS) {
      expect(root, token).toContain(`${token}:`)
    }
  })

  // Радиус от режима не зависит: задать его дважды значит однажды разойтись.
  it("радиус только в :root", () => {
    const css = buildThemeCss(blue)
    expect(block(css, ":root")).toContain("--radius: 0.5rem")
    expect(block(css, ".dark")).not.toContain("--radius")
  })

  it("подставляет значения темы, а не соседней", () => {
    const root = block(buildThemeCss(blue), ":root")
    expect(root).toContain(`--primary: ${blue.light.primary}`)
    expect(root).toContain(`--input: ${blue.light.border}`)
    expect(root).toContain(`--sidebar: ${blue.light.card}`)
  })

  it("собирается для каждой темы набора", () => {
    for (const theme of THEMES) {
      const root = block(buildThemeCss(theme), ":root")
      for (const token of ROOT_TOKENS) {
        expect(root, `${theme.name} ${token}`).toContain(`${token}:`)
      }
    }
  })

  // Тесты выше проверяют только наличие имени токена, не то, что за ним
  // стоит: --popover: ramp.background вместо ramp.card или --input:
  // ramp.ring вместо ramp.border прошли бы незамеченными. Сверка идёт по
  // теме-эталону и целым словарём: toEqual ловит и подменённое значение, и
  // лишний токен, и пропавший.
  it("отображает светлый режим эталона в сорок токенов :root", () => {
    const actual = parseDeclarations(block(buildThemeCss(SENTINEL), ":root"))
    expect(actual).toEqual({
      ...expectedDeclarations(SENTINEL.light, SHARED_COLORS.light),
      "--radius": SENTINEL.radius,
    })
  })

  // Если в css.ts перепутать местами theme.light и theme.dark при сборке
  // блока .dark, тесты выше остаются зелёными: имена токенов на месте, а
  // отображение сверяется только с :root. Тёмная тема стала бы копией
  // светлой, и заметить это можно было бы только глазами на контуре.
  it("отображает тёмный режим эталона и не путает его со светлым", () => {
    const actual = parseDeclarations(block(buildThemeCss(SENTINEL), ".dark"))
    expect(actual).toEqual(expectedDeclarations(SENTINEL.dark, SHARED_COLORS.dark))
  })
})
