import { describe, expect, it } from "vitest"
import { END_MARKER, START_MARKER, replaceThemeBlock } from "./apply"

const FILE = `@import "tailwindcss";

${START_MARKER}
:root {
    --primary: старое;
}
${END_MARKER}

@layer base {
  body { color: red; }
}
`

const THEME = `:root {\n    --primary: новое;\n}`

describe("replaceThemeBlock", () => {
  it("заменяет то, что между маркерами", () => {
    const out = replaceThemeBlock(FILE, THEME)
    expect(out).toContain("--primary: новое")
    expect(out).not.toContain("--primary: старое")
  })

  it("не трогает остальной файл", () => {
    const out = replaceThemeBlock(FILE, THEME)
    expect(out).toContain('@import "tailwindcss";')
    expect(out).toContain("body { color: red; }")
    expect(out).toContain(START_MARKER)
    expect(out).toContain(END_MARKER)
  })

  // Команду выполняют повторно — примерили одну тему, вернулись к прежней.
  // Без идемпотентности файл рос бы вложенными блоками при каждом прогоне.
  it("идемпотентна", () => {
    const once = replaceThemeBlock(FILE, THEME)
    expect(replaceThemeBlock(once, THEME)).toBe(once)
  })

  it("без маркеров бросает понятную ошибку, а не портит файл", () => {
    expect(() => replaceThemeBlock("@import 'tailwindcss';", THEME)).toThrow(
      /маркер/i
    )
  })

  // Мутация: убрать проверку `end < start` — все четыре теста выше
  // остаются зелёными, потому что ни один не строит файл с END_MARKER
  // раньше START_MARKER. Без этой проверки функция не бросает ошибку, а
  // молча режет файл по перепутанным индексам и портит его.
  it("маркер конца раньше маркера начала — тоже ошибка, а не порча файла", () => {
    const broken = `@import "tailwindcss";\n\n${END_MARKER}\n${START_MARKER}\n`
    expect(() => replaceThemeBlock(broken, THEME)).toThrow(/маркер/i)
  })

  // Мутация: убрать .trim() у подставляемого CSS — все четыре теста выше
  // остаются зелёными, потому что THEME в них уже без краевых переводов
  // строк. Без .trim() лишние пустые строки из buildThemeCss копятся в
  // globals.css при каждом прогоне.
  it("обрезает переводы строк по краям подставляемого CSS", () => {
    const out = replaceThemeBlock(FILE, `\n\n${THEME}\n\n`)
    expect(out).toContain(`${START_MARKER}\n${THEME}\n${END_MARKER}`)
  })

  it("пустой блок между маркерами — просто пусто, не ошибка", () => {
    const empty = `@import "x";\n${START_MARKER}\n${END_MARKER}\n`
    const out = replaceThemeBlock(empty, THEME)
    expect(out).toContain(`${START_MARKER}\n${THEME}\n${END_MARKER}`)
  })

  // Если маркеры в файле встречаются дважды, indexOf берёт первую пару —
  // функция не обязана чинить дублирование, но обязана не задевать
  // второй блок и не путать конец первого с концом второго.
  it("при повторе маркеров трогает только первую пару", () => {
    const duplicated =
      FILE + `\n${START_MARKER}\n:root { --primary: другое; }\n${END_MARKER}\n`
    const out = replaceThemeBlock(duplicated, THEME)
    expect(out).toContain("--primary: новое")
    expect(out).toContain("--primary: другое")
    expect(out).not.toContain("--primary: старое")
  })
})
