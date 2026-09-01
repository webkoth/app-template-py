import { expect, test } from "@playwright/test"

// Данные создаются внутри теста, а не берутся из сида: тест, зависящий от
// сида, ломается при любом изменении сида и не воспроизводится на пустой
// базе контура.
const unique = () => `e2e${Date.now()}${Math.floor(Math.random() * 1000)}`

test("незалогиненного уводит на форму входа", async ({ page }) => {
  await page.goto("/expenses")
  await expect(page.getByRole("heading", { name: "Вход" })).toBeVisible()
})

test("неверная пара не пускает и не выдаёт, существует ли логин", async ({
  page,
}) => {
  await page.goto("/login")
  await page.getByLabel("Логин").fill("нетакого")
  await page.getByLabel("Пароль").fill("мимо")
  await page.getByRole("button", { name: "Войти" }).click()
  await expect(page.getByText("Неверный логин или пароль")).toBeVisible()
})

test("вход и выход работают", async ({ page }) => {
  await page.goto("/login")
  await page.getByLabel("Логин").fill("admin")
  await page.getByLabel("Пароль").fill("admin")
  await page.getByRole("button", { name: "Войти" }).click()

  await expect(page.getByRole("heading", { level: 1 })).toBeVisible()
  // Предупреждение о паре по умолчанию обязано висеть на первом экране.
  await expect(
    page.getByText("Вход под учётной записью по умолчанию")
  ).toBeVisible()

  await page.getByRole("button", { name: "Выйти" }).click()
  await expect(page.getByRole("heading", { name: "Вход" })).toBeVisible()
})

test("роль viewer не видит раздел «Люди» и не попадает в него по адресу", async ({
  page,
}) => {
  const login = unique()

  await page.goto("/login")
  await page.getByLabel("Логин").fill("admin")
  await page.getByLabel("Пароль").fill("admin")
  await page.getByRole("button", { name: "Войти" }).click()
  // Клик по «Войти» только отправляет запрос. Без ожидания следующий
  // page.goto уходит раньше, чем приходит кука сессии: гейт уводит обратно
  // на форму входа, и сценарий падает на поле «Имя», которого там нет.
  // Проверено — без этой строки падал ровно так.
  await page.waitForURL("/")

  await page.goto("/users")
  await page.getByLabel("Логин").fill(login)
  await page.getByLabel("Имя").fill("Смотрящий")
  await page.getByLabel("Пароль").fill("длинныйпароль")
  await page.getByRole("button", { name: "Завести" }).click()
  await expect(page.getByRole("cell", { name: login })).toBeVisible()

  await page.getByRole("button", { name: "Выйти" }).click()
  // Ожидание перехода обязательно: подписи «Логин» и «Пароль» есть и на
  // форме заведения учётной записи, поэтому без него заполняется она —
  // страница ещё та же, — а на форму входа приезжают пустые поля, и вход
  // не происходит вовсе. Проверено: без этой строки сценарий вис на
  // ожидании перехода на главную.
  await page.waitForURL("/login")
  await page.getByLabel("Логин").fill(login)
  await page.getByLabel("Пароль").fill("длинныйпароль")
  await page.getByRole("button", { name: "Войти" }).click()
  // То же ожидание, что и выше, и по той же причине: без него проверка
  // ниже сходится на форме входа, где ссылки «Люди» нет ни у кого, — то
  // есть тест проходил бы, ничего не проверив.
  await page.waitForURL("/")

  await expect(page.getByRole("link", { name: "Люди" })).toHaveCount(0)

  // Вторая половина названия: по прямому адресу viewer в раздел тоже не
  // попадает. Форма заведения учётной записи ему не показывается, а список
  // бэкенд отдавать отказывается — и экран говорит об отказе, а не
  // притворяется пустым.
  await page.goto("/users")
  await expect(page.getByRole("button", { name: "Завести" })).toHaveCount(0)
  await expect(page.getByText("Недостаточно прав")).toBeVisible()
})
