import { useQuery } from "@tanstack/react-query"
import { api } from "@/api/client"
import { PageMain } from "@/components/page-main"
import { Badge } from "@/components/ui/badge"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { formatDateTime } from "@/lib/format"

const ACTION_LABEL: Record<string, string> = {
  create: "создание",
  update: "изменение",
  delete: "удаление",
}

export function AuditPage() {
  const entries = useQuery({
    queryKey: ["audit"],
    queryFn: async () => (await api.GET("/api/audit")).data ?? [],
  })

  return (
    <PageMain>
      <h1 className="text-3xl font-semibold">Журнал</h1>
      <p className="text-muted-foreground mt-2 max-w-2xl text-sm">
        Каждая мутация данных пишется сюда той же транзакцией, что и само
        изменение. Показаны последние двести записей.
      </p>

      <Table className="mt-6">
        <TableHeader>
          <TableRow>
            <TableHead>Когда</TableHead>
            <TableHead>Кто</TableHead>
            <TableHead>Что</TableHead>
            <TableHead>Объект</TableHead>
            <TableHead>Подробности</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {entries.data?.length === 0 && (
            <TableRow>
              <TableCell colSpan={5} className="text-muted-foreground py-8 text-center">
                Записей пока нет — в журнал попадают только изменения данных.
              </TableCell>
            </TableRow>
          )}
          {entries.data?.map((entry) => (
            <TableRow key={entry.id}>
              <TableCell className="text-muted-foreground whitespace-nowrap">
                {formatDateTime(entry.ts)}
              </TableCell>
              <TableCell className="font-medium">{entry.actor}</TableCell>
              <TableCell>
                <Badge variant="secondary">
                  {ACTION_LABEL[entry.action] ?? entry.action}
                </Badge>
              </TableCell>
              <TableCell>{entry.entity}</TableCell>
              <TableCell className="text-muted-foreground">{entry.detail}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </PageMain>
  )
}
