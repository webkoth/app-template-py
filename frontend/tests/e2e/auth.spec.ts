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

  // Сначала опора, потом отсутствие. `toHaveCount(0)` сходится и на ещё не
  // отрисованной странице: адрес меняет роутер, а меню React дорисовывает
  // после — то есть проверка «ссылки нет» проходила бы и на пустом экране.
  // Показано мутацией: ссылка «Люди», выданная роли editor, оставляла
  // сценарий зелёным. Видимая соседняя ссылка означает, что меню уже здесь и
  // отсутствие «Людей» — настоящее.
  await expect(page.getByRole("link", { name: "Расходы" })).toBeVisible()
  await expect(page.getByRole("link", { name: "Люди" })).toHaveCount(0)

  // Вторая половина названия: по прямому адресу viewer в раздел тоже не
  // попадает. Форма заведения учётной записи ему не показывается, а список
  // бэкенд отдавать отказывается — и экран говорит об отказе, а не
  // притворяется пустым.
  await page.goto("/users")
  await expect(page.getByRole("button", { name: "Завести" })).toHaveCount(0)
  await expect(page.getByText("Недостаточно прав")).toBeVisible()
})

test("роль editor правит расходы, но раздел «Люди» ей не показан", async ({
  page,
}) => {
  // Средняя роль не была покрыта сквозным сценарием вовсе: все прочие
  // входят под admin, а единственный ролевой сценарий проверяет viewer. То
  // есть «editor правит расходы, но людьми не управляет» держали только
  // API-тесты, и разъехаться клиентский гейт с сервером мог молча —
  // например, потеряв editor в списке ролей формы.
  const login = unique()

  await page.goto("/login")
  await page.getByLabel("Логин").fill("admin")
  await page.getByLabel("Пароль").fill("admin")
  await page.getByRole("button", { name: "Войти" }).click()
  await page.waitForURL("/")

  await page.goto("/users")
  await page.getByLabel("Логин").fill(login)
  await page.getByLabel("Имя").fill("Правящий")
  // Роль выбирается явно: по умолчанию форма заводит viewer, и без этого
  // клика сценарий проверял бы вторую копию соседнего теста.
  //
  // Локатор по роли элемента, а не getByLabel("Роль"): подписи сопоставляются
  // подстрокой без учёта регистра, и «Роль» находится внутри «Пароль» — два
  // совпадения и отказ strict mode. Проверено, падало ровно так.
  await page.getByRole("combobox", { name: "Роль" }).click()
  await page.getByRole("option", { name: "Правит" }).click()
  await page.getByLabel("Пароль").fill("длинныйпароль")
  await page.getByRole("button", { name: "Завести" }).click()
  await expect(page.getByRole("cell", { name: login })).toBeVisible()

  await page.getByRole("button", { name: "Выйти" }).click()
  await page.waitForURL("/login")
  await page.getByLabel("Логин").fill(login)
  await page.getByLabel("Пароль").fill("длинныйпароль")
  await page.getByRole("button", { name: "Войти" }).click()
  await page.waitForURL("/")

  // Опора перед отсутствием — по той же причине, что и в сценарии viewer.
  await expect(page.getByRole("link", { name: "Расходы" })).toBeVisible()
  await expect(page.getByRole("link", { name: "Люди" })).toHaveCount(0)

  // Главное отличие от viewer: форма расходов показана, и расход
  // действительно сохраняется — то есть бэкенд тоже пустил.
  await page.goto("/expenses")
  const title = `Правка ${Date.now()}`
  await page.getByLabel("Дата").fill("2026-08-31")
  await page.getByLabel("Назначение").fill(title)
  await page.getByLabel("Сумма").fill("321")
  await page.getByRole("button", { name: "Добавить" }).click()
  await expect(page.getByRole("cell", { name: title })).toBeVisible()
})

test("лежащий бэкенд показывает отказ, а не форму входа", async ({ page }) => {
  // Разница между «вы не вошли» и «сервер не отвечает» дороже, чем кажется:
  // первое человек лечит паролем, второе — звонком. Пока запрос «кто вошёл»
  // читался как `data ?? null`, 500 и 502 давали то же самое null, что и
  // 401, роутер уводил на форму входа, и владелец набирал верный пароль
  // снова и снова. Это был единственный вызов api мимо `unwrap`.
  //
  // Отказ подставляется браузером, а не остановкой сервера: сервер общий на
  // весь прогон, и его остановка уронила бы соседние сценарии.
  await page.route("**/api/auth/me", (route) =>
    route.fulfill({
      status: 500,
      contentType: "application/json",
      body: JSON.stringify({ error: "Что-то пошло не так" }),
    })
  )

  await page.goto("/")

  await expect(page.getByText("Приложение не отвечает")).toBeVisible()
  await expect(page.getByText("Что-то пошло не так")).toBeVisible()
  await expect(page.getByRole("heading", { name: "Вход" })).toHaveCount(0)
})
