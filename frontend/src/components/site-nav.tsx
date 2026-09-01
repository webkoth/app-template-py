import { Link, useNavigate } from "@tanstack/react-router"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { LogOut } from "lucide-react"
import { api } from "@/api/client"
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
      await api.POST("/api/auth/logout")
    },
    onSuccess: async () => {
      // Кэш сбрасывается целиком: в нём лежат данные, которые следующему
      // вошедшему видеть незачем.
      queryClient.clear()
      await navigate({ to: "/login" })
    },
  })

  return (
    <header className="border-border border-b">
      <nav className="mx-auto flex max-w-5xl items-center gap-1 px-4 py-3">
        {LINKS.filter((link) => hasRank(user.role, link.role)).map((link) => (
          <Link
            key={link.to}
            to={link.to}
            className="text-muted-foreground hover:text-foreground rounded-md px-3 py-1.5 text-sm"
            activeProps={{ className: "text-foreground font-medium" }}
          >
            {link.label}
          </Link>
        ))}
        <span className="text-muted-foreground ml-auto text-sm">{user.name}</span>
        <Button
          variant="ghost"
          size="icon"
          aria-label="Выйти"
          onClick={() => logout.mutate()}
        >
          <LogOut className="size-4" />
        </Button>
      </nav>
    </header>
  )
}
