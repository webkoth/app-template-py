/**
 * Применение темы: npm run theme -- <имя>
 *
 * Единственное место с вводом-выводом. Вся логика — в чистых функциях
 * lib/design, и они же покрыты тестами.
 *
 * prettier в этом проекте форматирует только ts и tsx, до src/index.css не
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
const THEME_CSS = fileURLToPath(new URL("../src/index.css", import.meta.url))

// Так файл с темой называется в СОСЕДНЕМ шаблоне на Next.js. Каталог
// src/lib/design копируется оттуда побайтово — это сознательное решение: два
// шаблона сверяются между собой обычным diff, и любая правка в общем каталоге
// превращает сверку в шум. Поэтому имя чужого файла остаётся в тексте ошибки
// там, а подменяется здесь — в единственном месте, которое знает настоящий
// путь. Размен честный: расхождение стоило бы шума при каждой сверке двух
// шаблонов, а сообщение про несуществующий файл — получаса поисков у того,
// кто его увидит.
const FOREIGN_NAME = "app/globals.css"

function list(): string {
  return THEMES.map(
    (theme) => `  ${theme.name.padEnd(10)} ${theme.label}`
  ).join("\n")
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

const css = readFileSync(THEME_CSS, "utf8")

let updated: string
try {
  updated = replaceThemeBlock(css, buildThemeCss(theme))
} catch (error) {
  // Ошибка приходит из общего с соседним шаблоном кода и называет его файл.
  // Ветка «имени не нашлось» нужна не для красоты: изменись текст там — и
  // молчаливая подмена перестала бы срабатывать, а сообщение снова
  // указывало бы не туда. Здесь оно в любом случае называет настоящий путь.
  const message = error instanceof Error ? error.message : String(error)
  console.error(
    message.includes(FOREIGN_NAME)
      ? message.replaceAll(FOREIGN_NAME, THEME_CSS)
      : `${message}\n\nФайл: ${THEME_CSS}`
  )
  process.exit(1)
}

writeFileSync(THEME_CSS, updated, "utf8")
console.log(`Тема «${theme.label}» применена в ${THEME_CSS}.`)
console.log("Проверь глазами: npm run dev, обе темы, светлая и тёмная.")
console.log("На контур правка уедет только через /ship.")
