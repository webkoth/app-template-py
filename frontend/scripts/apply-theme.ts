/**
 * Применение темы: npm run theme -- <имя>
 *
 * Единственное место с вводом-выводом. Вся логика — в чистых функциях
 * lib/design, и они же покрыты тестами.
 *
 * prettier в этом проекте форматирует только ts и tsx, до globals.css не
 * доходит: текст, который пишет buildThemeCss, обязан быть опрятным сразу —
 * переформатировать его потом нечем.
 */
import { readFileSync, writeFileSync } from "node:fs"
import { fileURLToPath } from "node:url"
import { replaceThemeBlock } from "../src/lib/design/apply"
import { buildThemeCss } from "../src/lib/design/css"
import { THEMES, findTheme } from "../src/lib/design/themes"

// Резолвится от расположения самого скрипта, а не от текущего каталога:
// запуск не из корня репозитория (например, `npx tsx scripts/apply-theme.ts`
// из другого места) иначе давал бы сырой ENOENT вместо внятного отказа.
const GLOBALS = fileURLToPath(new URL("../src/index.css", import.meta.url))

function list(): string {
  return THEMES.map((theme) => `  ${theme.name.padEnd(10)} ${theme.label}`).join("\n")
}

const name = process.argv[2]

if (!name) {
  console.error(`Укажи тему: npm run theme -- <имя>\n\nДоступные:\n${list()}`)
  process.exit(1)
}

const theme = findTheme(name)
if (!theme) {
  console.error(`Темы «${name}» нет.\n\nДоступные:\n${list()}`)
  process.exit(1)
}

const css = readFileSync(GLOBALS, "utf8")
writeFileSync(GLOBALS, replaceThemeBlock(css, buildThemeCss(theme)), "utf8")
console.log(`Тема «${theme.label}» применена в ${GLOBALS}.`)
console.log("Проверь глазами: npm run dev, обе темы, светлая и тёмная.")
console.log("На контур правка уедет только через /ship.")
