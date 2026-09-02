/**
 * Замена блока темы в app/globals.css. Чистая функция: весь ввод-вывод
 * держит scripts/apply-theme.ts.
 *
 * Границей служат маркеры-комментарии, а не поиск «:root {» по тексту:
 * :root встречается и в других местах файла, и однажды скрипт заменил бы
 * не то. Маркер — это явный договор файла со скриптом.
 */

export const START_MARKER =
  "/* theme:start — не править руками, см. npm run theme */"
export const END_MARKER = "/* theme:end */"

export function replaceThemeBlock(css: string, themeCss: string): string {
  const start = css.indexOf(START_MARKER)
  const end = css.indexOf(END_MARKER)

  if (start < 0 || end < 0 || end < start) {
    throw new Error(
      `В app/globals.css не найдены маркеры темы.\n` +
        `Ожидались строки:\n  ${START_MARKER}\n  ${END_MARKER}\n` +
        `Без них неясно, что заменять, и переписывать файл наугад нельзя.`
    )
  }

  return (
    css.slice(0, start + START_MARKER.length) +
    "\n" +
    themeCss.trim() +
    "\n" +
    css.slice(end)
  )
}
