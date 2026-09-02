#!/usr/bin/env node
/**
 * Проверка готовности установки. Печатает, чего не хватает, и завершается
 * ненулевым кодом, если установка не закончена.
 *
 * Читает окружение сам: запускается до того, как приложение существует, —
 * значит без зависимостей, только node.
 *
 * Пути считаются от самого файла, а не от текущего каталога: скрипт зовут
 * и из корня, и из `frontend`, и из редактора, у которого свой cwd. По
 * относительным путям он в этих случаях молча проверял бы пустоту и
 * докладывал бы об успехе.
 *
 * В самом шаблоне (а не в установке из него) часть строк законно красная:
 * ни переименования, ни заполненной анкеты, ни удалённых блоков
 * Bootstrap-Only здесь нет и не будет. Это не поломка скрипта.
 */
import { execSync } from "node:child_process"
import { existsSync, readFileSync } from "node:fs"
import { dirname, join, resolve } from "node:path"
import { fileURLToPath } from "node:url"

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..")

const checks = []

function check(label, ok, hint = "") {
  checks.push({ label, ok, hint })
}

function version(command) {
  try {
    return execSync(command, { cwd: root, stdio: ["ignore", "pipe", "ignore"] })
      .toString()
      .trim()
  } catch {
    return null
  }
}

function read(relative) {
  const path = join(root, relative)
  return existsSync(path) ? readFileSync(path, "utf8") : null
}

check("git установлен", version("git --version") !== null)
check("gh установлен", version("gh --version") !== null, "brew install gh")
check(
  "uv установлен",
  version("uv --version") !== null,
  "curl -LsSf https://astral.sh/uv/install.sh | sh"
)
check("node установлен", version("node --version") !== null)
check("psql установлен", version("psql --version") !== null)
// Make отдельной строкой: на macOS и Linux он есть всегда, а в Windows не
// входит в систему вовсе и приезжает с Git Bash. Без него не работает ни
// одна команда проекта — все они идут через Makefile.
check("make установлен", version("make --version") !== null, "в Windows — Git Bash или MSYS2")

const env = read(".env")
check(".env создан", env !== null, "cp .env.example .env")

if (env !== null) {
  const secret = env.match(/^APP_AUTH_SECRET="?([^"\n]*)"?/m)?.[1] ?? ""
  check(
    "APP_AUTH_SECRET задан",
    secret.length >= 32,
    "openssl rand -hex 32 и вписать в .env"
  )
}

// Пустой ответ — это отсутствующий origin, а не шаблонный. По шагу E
// установки репозитория может ещё не быть: это допустимое состояние, а
// красная строка здесь означала бы «почини то, что чинить не время».
const remote = version("git remote get-url origin") ?? ""
check(
  "origin отвязан от шаблона",
  !remote.includes("app-template-py"),
  "git remote set-url origin <адрес своего репозитория>"
)

// Переименование. Проверяются только владеющие источники из таблицы шага D,
// а не весь репозиторий: слово `apptemplatepy` законно остаётся в текстах
// установки (`docs/commands/onboarding.md` показывает им же поиск) и в
// планах со спеками, которые описывают историю шаблона, а не это
// приложение. Имя репозитория-источника `app-template-py` пишется через
// дефисы и под эту проверку не попадает — README и промпт для агента её
// проходят.
const owned = [
  "backend/pyproject.toml",
  "backend/uv.lock",
  "backend/app/main.py",
  ".env.example",
  ".github/workflows/ci.yml",
  ".github/workflows/deploy.yml",
  ".github/workflows/backup.yml",
  "AGENTS.md",
  // Заголовок вкладки браузера. Его видит каждый, кто открыл приложение, а
  // забывают его чаще прочего: в списке файлов он выглядит разметкой.
  "frontend/index.html",
]
const stale = owned.filter((file) => read(file)?.includes("apptemplatepy"))
check("переименование", stale.length === 0, stale.join(", "))

const bootstrapLeft =
  read("AGENTS.md")?.includes("BOOTSTRAP_ONLY_START") ||
  read("CLAUDE.md")?.includes("BOOTSTRAP_ONLY_START")
check(
  "блоки Bootstrap-Only удалены",
  !bootstrapLeft,
  "удалить блок из AGENTS.md и CLAUDE.md — последний шаг установки"
)

// Считаются только строки таблиц и пунктов списка. Легенда в начале файла
// объясняет сам маркер («Ячейки ответов держат `_не отвечено_`…»), и поиск
// по всему тексту не позеленел бы никогда — даже у полностью заполненной
// анкеты.
const checklist = read("CHECKLIST.md")
const unanswered = (checklist ?? "")
  .split("\n")
  .filter((line) => /^\s*(\||- \[)/.test(line) && line.includes("_не отвечено_"))
check(
  "CHECKLIST.md заполнен",
  checklist !== null && unanswered.length === 0,
  unanswered.length > 0 ? `без ответа: ${unanswered.length}` : "файла нет"
)

const width = Math.max(...checks.map(({ label }) => label.length))

let failed = 0
for (const { label, ok, hint } of checks) {
  const status = ok ? "OK " : "НЕТ"
  const tail = !ok && hint ? `  — ${hint}` : ""
  console.log(`  ${status}  ${tail ? label.padEnd(width) : label}${tail}`)
  if (!ok) failed += 1
}

console.log("")
console.log(failed === 0 ? "Установка завершена." : `Осталось шагов: ${failed}`)
process.exit(failed === 0 ? 0 : 1)
