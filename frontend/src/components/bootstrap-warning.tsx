import { TriangleAlert } from "lucide-react"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import type { CurrentUser } from "@/lib/auth"

/**
 * Пара admin / admin известна всем, у кого есть шаблон. Предупреждение
 * висит, пока под ней работают: контур открыт снаружи.
 */
export function BootstrapWarning({ user }: { user: CurrentUser }) {
  // Признак считает сервер. Сравнение с литералом "admin" промахивалось бы в
  // обе стороны: при своём имени учётной записи предупреждение не показалось
  // бы никогда, а владелец, назвавший собственную запись admin, видел бы его
  // вечно — и перестал бы читать предупреждения вообще.
  if (!user.using_bootstrap_account) return null
  return (
    <Alert variant="destructive" className="mb-6">
      <TriangleAlert className="size-4" />
      <AlertTitle>Вход под учётной записью по умолчанию</AlertTitle>
      <AlertDescription>
        Пара admin / admin известна всем, у кого есть шаблон. Заведи свою
        учётную запись в разделе «Люди», войди под ней и отключи эту. Смены
        пароля в приложении нет намеренно.
      </AlertDescription>
    </Alert>
  )
}
