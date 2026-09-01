import { Link } from "@tanstack/react-router"
import { useSuspenseQuery } from "@tanstack/react-query"
import { BootstrapWarning } from "@/components/bootstrap-warning"
import { PageMain } from "@/components/page-main"
import { buttonVariants } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { currentUserQuery, hasRank } from "@/lib/auth"

const SECTIONS = [
  {
    to: "/expenses",
    title: "Расходы",
    text: "Образцовый раздел. Показывает, как устроена фича целиком.",
    role: "viewer" as const,
  },
  {
    to: "/users",
    title: "Люди",
    text: "Учётные записи, роли и отключение доступа.",
    role: "admin" as const,
  },
  {
    to: "/docs",
    title: "Правила",
    text: "Как здесь работают: правила проекта и команды доставки.",
    role: "viewer" as const,
  },
]

export function HomePage() {
  const { data: user } = useSuspenseQuery(currentUserQuery)
  if (!user) return null

  return (
    <PageMain>
      <BootstrapWarning user={user} />
      <h1 className="text-3xl font-semibold">Стартовый шаблон на Python</h1>
      <p className="text-muted-foreground mt-2 max-w-2xl">
        Это заготовка внутреннего приложения: вход, роли, журнал аудита и
        образцовая фича. Когда появится первая настоящая функция, эту
        страницу переписывают под неё — сам маршрут несущий, сюда ведёт вход.
      </p>
      <div className="mt-8 grid gap-4 sm:grid-cols-2">
        {SECTIONS.filter((s) => hasRank(user.role, s.role)).map((section) => (
          <Card key={section.to}>
            <CardHeader>
              <CardTitle>{section.title}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <p className="text-muted-foreground text-sm">{section.text}</p>
              {/* Ссылка стилизуется классами buttonVariants, а не Button с
                  render: Base UI поверх render всё равно ставит
                  role="button", и для скринридера это перестаёт быть
                  ссылкой. */}
              <Link
                to={section.to}
                className={buttonVariants({ variant: "outline", size: "sm" })}
              >
                Открыть
              </Link>
            </CardContent>
          </Card>
        ))}
      </div>
    </PageMain>
  )
}
