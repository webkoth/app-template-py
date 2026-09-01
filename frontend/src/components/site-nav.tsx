import { Link, useNavigate } from "@tanstack/react-router"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { LogOut } from "lucide-react"
import { api, unwrap } from "@/api/client"
import { RequestFailure } from "@/components/request-failure"
import { Button } from "@/components/ui/button"
import { hasRank, type CurrentUser } from "@/lib/auth"

// as const обязателен: без него `to` выводится как string, и
// типизированные ссылки TanStack Router перестают проверяться — ровно та
// проверка, ради которой роутер и выбран.
const LINKS = [
  { to: "/", label: "Главная", role: "viewer" as const },
  { to: "/expenses", label: "Расходы", role: "viewer" as const },
  { to: "/users", label: "Люди", role: "admin" as const },
  { to: "/audit", label: "Журнал", role: "admin" as const },
  { to: "/design", label: "Дизайн", role: "viewer" as const },
  { to: "/docs", label: "Правила", role: "viewer" as const },
] as const

export function SiteNav({ user }: { user: CurrentUser }) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const logout = useMutation({
    mutationFn: async () => {
      // Ответ проверяется, а не выбрасывается. Куку гасит сервер: без
      // проверки интерфейс «выходил» при недоступном сервере, а кука
      // оставалась живой — следующий переход молча возвращал бы человека
      // в приложение под той же учётной записью. Хуже всего это на чужом
      // компьютере, где выход и нажимают.
      unwrap(await api.POST("/api/auth/logout"))
    },
    onSuccess: async () => {
      // Кэш сбрасывается целиком: в нём лежат данные, которые следующему
      // вошедшему видеть незачем.
      queryClient.clear()
      await navigate({ to: "/login" })
    },
  })

  return (
    <header className="border-b border-border">
      <nav className="mx-auto flex max-w-5xl items-center gap-1 px-4 py-3">
        {LINKS.filter((link) => hasRank(user.role, link.role)).map((link) => (
          <Link
            key={link.to}
            to={link.to}
            className="rounded-md px-3 py-1.5 text-sm text-muted-foreground hover:text-foreground"
            activeProps={{ className: "text-foreground font-medium" }}
          >
            {link.label}
          </Link>
        ))}
        <span className="ml-auto text-sm text-muted-foreground">
          {user.name}
        </span>
        <Button
          variant="ghost"
          size="icon"
          aria-label="Выйти"
          onClick={() => logout.mutate()}
        >
          <LogOut className="size-4" />
        </Button>
      </nav>
      {logout.isError && (
        // Отказ выхода показывается на месте, а не в тишине: человек
        // нажал «Выйти», и молчание он прочитает как «вышел».
        <RequestFailure
          error={logout.error}
          title="Не удалось выйти"
          className="mx-auto max-w-5xl rounded-none border-x-0 border-t-0"
        />
      )}
    </header>
  )
}
