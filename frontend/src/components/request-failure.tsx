import { toApiError } from "@/api/client"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { cn } from "@/lib/utils"

/**
 * Показ отказа сервера на экране со списком.
 *
 * Общий компонент, а не развилка по месту: «данные или отказ» повторяется
 * на каждом экране, и написанная руками по четвёртому разу она разъедется —
 * где-то покажут причину, где-то оставят пустую таблицу. Разъехалось уже
 * один раз: списки читались как `(await api.GET(...)).data ?? []`, отказ
 * превращался в пустой массив, и viewer, зашедший по прямой ссылке на
 * /users, видел «Учётных записей пока нет» — при том что пришёл 403.
 *
 * Заголовок отдельно от текста намеренно: сервер отвечает «Недостаточно
 * прав» или «Сервер недоступен», и без «Не удалось загрузить» рядом
 * непонятно, что именно не получилось.
 */
export function RequestFailure({
  error,
  title = "Не удалось загрузить",
  className,
}: {
  error: unknown
  title?: string
  className?: string
}) {
  return (
    <Alert variant="destructive" className={cn(className)}>
      <AlertTitle>{title}</AlertTitle>
      <AlertDescription>{toApiError(error).message}</AlertDescription>
    </Alert>
  )
}
