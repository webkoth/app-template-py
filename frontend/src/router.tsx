import type { JSX } from "react"
import {
  createRootRouteWithContext,
  createRoute,
  createRouter,
  lazyRouteComponent,
  Outlet,
  redirect,
} from "@tanstack/react-router"
import type { QueryClient } from "@tanstack/react-query"
import { currentUserQuery } from "@/lib/auth"
import { PageMain } from "@/components/page-main"
import { RequestFailure } from "@/components/request-failure"
import { SiteNav } from "@/components/site-nav"
import { AuditPage } from "@/routes/audit"
import { ExpensesPage } from "@/routes/expenses"
import { HomePage } from "@/routes/home"
import { LoginPage } from "@/routes/login"
import { UsersPage } from "@/routes/users"

interface RouterContext {
  queryClient: QueryClient
}

const rootRoute = createRootRouteWithContext<RouterContext>()({
  component: Outlet,
})

const loginRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/login",
  component: LoginPage,
})

/**
 * Оболочка закрытой части. beforeLoad уводит на /login, если сессии нет.
 *
 * ЭТО НЕ ЗАЩИТА. Гейт нужен, чтобы человек видел форму входа вместо пустого
 * экрана. Данные защищает бэкенд: каждый роутер там проверяет роль сам,
 * включая маршруты, куда этот интерфейс не ведёт.
 */
const privateRoute = createRoute({
  getParentRoute: () => rootRoute,
  id: "private",
  beforeLoad: async ({ context }) => {
    const user = await context.queryClient.ensureQueryData(currentUserQuery)
    if (!user) throw redirect({ to: "/login" })
    return { user }
  },
  // Отказ на пути «кто вошёл» показывается, а не уводит на форму входа.
  // Запрос отвечает null только на 401 — «не вошёл», — а всё остальное
  // (500, 502, обрыв) бросает; без этого экрана бросок дошёл бы до
  // умолчания роутера, а оно написано по-английски и для разработчика.
  // Переброс на /login сюда не попадает: роутер разбирает его до
  // errorComponent.
  errorComponent: ({ error }) => (
    <PageMain>
      <RequestFailure title="Приложение не отвечает" error={error} />
    </PageMain>
  ),
  component: function PrivateLayout() {
    const { user } = privateRoute.useRouteContext()
    return (
      <>
        <SiteNav user={user} />
        <Outlet />
      </>
    )
  },
})

// Параметр обобщённый, а не `path: string`. С `string` литерал пути теряется
// на входе в помощник, дерево маршрутов собирается с путём-строкой, и
// типизированные ссылки знают только «/» и «/login»: `to="/expenses"` не
// собирается, а `to="/выдуманное"` проходит. Замерено: с `path: string`
// tsc падает на SiteNav, с обобщённым — ноль ошибок, а зонд на
// несуществующий путь падает.
// `JSX.Element | null`, а не просто `JSX.Element`: currentUserQuery по типу
// отдаёт `CurrentUser | null`, и страница закрытой части сужает его
// охранником `if (!user) return null`. Ветка недостижима — сюда пускает
// beforeLoad, который без сессии уводит на /login, — но компилятор её
// требует, и без этого допущения ни одна такая страница в помощник не
// проходит.
const page = <TPath extends string>(
  path: TPath,
  component: () => JSX.Element | null
) => createRoute({ getParentRoute: () => privateRoute, path, component })

// Витрина и правила грузятся отдельно от остального. Они тянут за собой
// recharts и react-markdown — вдвое больше всего прочего вместе взятого
// (замерено: 572 кБ против 1245 кБ одним куском), а заходят на них редко и
// не в работе: витрину однажды удаляют целиком, правила читают раз в месяц.
// Одним куском сборка выходила за порог Vite, и предупреждение печаталось
// при каждом прогоне — предупреждение, которое видишь всегда, перестают
// читать вообще.
const lazyPage = <TPath extends string>(
  path: TPath,
  load: () => Promise<Record<string, unknown>>,
  name: string
) =>
  createRoute({
    getParentRoute: () => privateRoute,
    path,
    component: lazyRouteComponent(load as never, name as never),
  })

const routeTree = rootRoute.addChildren([
  loginRoute,
  privateRoute.addChildren([
    page("/", HomePage),
    page("/expenses", ExpensesPage),
    page("/users", UsersPage),
    page("/audit", AuditPage),
    lazyPage("/design", () => import("@/routes/design"), "DesignPage"),
    lazyPage("/docs", () => import("@/routes/docs"), "DocsPage"),
  ]),
])

export function buildRouter(queryClient: QueryClient) {
  return createRouter({ routeTree, context: { queryClient } })
}

declare module "@tanstack/react-router" {
  interface Register {
    router: ReturnType<typeof buildRouter>
  }
}
