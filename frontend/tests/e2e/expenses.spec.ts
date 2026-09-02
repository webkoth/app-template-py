import { expect, test } from "@playwright/test"

test.beforeEach(async ({ page }) => {
  await page.goto("/login")
  await page.getByLabel("Логин").fill("admin")
  await page.getByLabel("Пароль").fill("admin")
  await page.getByRole("button", { name: "Войти" }).click()
  // Клик по «Войти» только отправляет запрос. Без ожидания перехода
  // следующий page.goto уходит раньше, чем приходит кука сессии: гейт
  // возвращает на форму входа, и каждый сценарий падает на поле «Дата»,
  // которого там нет. Проверено — без этой строки падали все пять.
  await page.waitForURL("/")
  await page.goto("/expenses")
})

test("расход добавляется и появляется в таблице", async ({ page }) => {
  const title = `Подписка ${Date.now()}`

  await page.getByLabel("Дата").fill("2026-08-31")
  await page.getByLabel("Назначение").fill(title)
  await page.getByLabel("Сумма").fill("1 200,50")
  await page.getByRole("button", { name: "Добавить" }).click()

  await expect(page.getByRole("cell", { name: title })).toBeVisible()
  // Сумма проверяется в строке СВОЕГО расхода, а не по всей таблице. База
  // e2e между прогонами не чистится, и на втором же прогоне ячеек
  // «1 200,50 ₽» становится две — strict mode Playwright падает на двух
  // совпадениях. В CI база каждый раз новая, поэтому там это молчало бы, а
  // на машине разработчика падал бы каждый второй прогон. Воспроизведено.
  const row = page.getByRole("row").filter({ hasText: title })
  await expect(row.getByRole("cell", { name: /1\s?200,50/ })).toBeVisible()
})

test("без даты расход не создаётся", async ({ page }) => {
  // Здесь НЕ проверяется правило «31 февраля не существует». Через браузер
  // до него не добраться: поле type="date" невозможную дату не принимает
  // вовсе — `fill("2026-02-31")` падает с «Malformed value», а набор с
  // клавиатуры оставляет поле пустым. Проверено.
  //
  // Само правило живёт на сервере и закреплено там: `parse_date_input_value`
  // и тест `test_impossible_date_rejected`. Оно нужно не ради браузера, а
  // ради всех прочих способов позвать API — и именно поэтому разбор даты
  // авторитетен на сервере, а не в форме.
  //
  // Браузеру остаётся своя половина: пустую дату форма не отправляет.
  await page.getByLabel("Назначение").fill("Не должно сохраниться")
  await page.getByLabel("Сумма").fill("100")
  await page.getByRole("button", { name: "Добавить" }).click()

  await expect(page.getByText("Укажи дату")).toBeVisible()
  await expect(
    page.getByRole("cell", { name: "Не должно сохраниться" })
  ).toHaveCount(0)
})

test("сумма сверх предела отклоняется с читаемым сообщением", async ({
  page,
}) => {
  await page.getByLabel("Дата").fill("2026-08-31")
  await page.getByLabel("Назначение").fill("Слишком много")
  await page.getByLabel("Сумма").fill("99000000")
  await page.getByRole("button", { name: "Добавить" }).click()

  await expect(page.getByText(/больше предельной/)).toBeVisible()
})

test("сводка обновляется вместе с таблицей", async ({ page }) => {
  // Сводка приходит отдельным запросом, и забытая инвалидация оставляет её
  // прежней: цифра на экране есть, но она врёт — а таблица рядом уже
  // правильная, поэтому глазами это не ловится.
  //
  // Сравнивается «до» и «после», а не конкретное значение: база e2e общая
  // для всех сценариев, и точная сумма зависит от порядка прогона.
  const total = page.getByTestId("expenses-total")
  const before = await total.textContent()

  await page.getByLabel("Дата").fill("2026-08-31")
  await page.getByLabel("Назначение").fill(`Сводка ${Date.now()}`)
  await page.getByLabel("Сумма").fill("777")
  await page.getByRole("button", { name: "Добавить" }).click()

  await expect(total).not.toHaveText(before ?? "")
})

test("изменение попадает в журнал", async ({ page }) => {
  const title = `В журнал ${Date.now()}`
  // Сумма уникальна для прогона, и она единственное, что связывает запись
  // журнала с этим расходом: назначения журнал не показывает — в подробности
  // уезжает «<категория>, <копейки> коп.».
  //
  // Раньше проверка искала ячейку «admin» и слово «создание» по всей таблице,
  // ни с чем их не связывая. Такую же пару оставляет заведение учётной записи
  // в соседнем сценарии, а база e2e между прогонами не чистится — то есть
  // проверка оставалась бы зелёной, даже если бы этот расход в журнал не
  // попал вовсе. Воспроизведено ревью.
  const kopecks = 100_000 + Math.floor(Math.random() * 800_000)
  const amount = (kopecks / 100).toFixed(2).replace(".", ",")

  await page.getByLabel("Дата").fill("2026-08-31")
  await page.getByLabel("Назначение").fill(title)
  await page.getByLabel("Сумма").fill(amount)
  await page.getByRole("button", { name: "Добавить" }).click()
  await expect(page.getByRole("cell", { name: title })).toBeVisible()

  await page.goto("/audit")
  // «Софт» — категория по умолчанию в форме. Вместе с суммой она даёт целую
  // строку подробностей, а не подстроку внутри чужого числа.
  const row = page.getByRole("row").filter({ hasText: `Софт, ${kopecks} коп.` })
  await expect(row).toHaveCount(1)
  await expect(row.getByRole("cell", { name: "admin" })).toBeVisible()
  await expect(row.getByRole("cell", { name: "создание" })).toBeVisible()
  await expect(row.getByRole("cell", { name: "расход" })).toBeVisible()
})
