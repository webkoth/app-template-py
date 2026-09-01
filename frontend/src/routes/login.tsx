// Заглушка. Настоящий экран пишется своей задачей — до тех пор страница
// существует, чтобы дерево маршрутов собиралось и `make check` оставался
// зелёным: иначе проверка типов красная шесть задач подряд, и понять, что
// именно сломала очередная правка, нечем.
import { PageMain } from "@/components/page-main"

export function LoginPage() {
  return (
    <PageMain>
      <h1 className="text-3xl font-semibold">Вход</h1>
    </PageMain>
  )
}
