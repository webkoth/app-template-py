import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { z } from "zod"
import { api, toApiError } from "@/api/client"
import { PageMain } from "@/components/page-main"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { formatDate, formatMoney } from "@/lib/format"

const CATEGORIES = ["Аренда", "Софт", "Оборудование", "Услуги", "Прочее"] as const

const schema = z.object({
  date: z.string().min(1, "Укажи дату"),
  title: z.string().min(1, "Укажи назначение"),
  category: z.enum(CATEGORIES),
  amount: z.string().min(1, "Укажи сумму"),
})

type Values = z.infer<typeof schema>

export function ExpensesPage() {
  const queryClient = useQueryClient()
  const expenses = useQuery({
    queryKey: ["expenses"],
    queryFn: async () => (await api.GET("/api/expenses")).data ?? [],
  })

  // Сводка считается на сервере, а не из уже загруженного списка. Список
  // однажды станет страничным, и подсчёт по нему тихо превратится в «итого
  // по первой странице» — цифра останется, смысл уйдёт.
  //
  // Ключ вложен в ["expenses"]: invalidateQueries по этому префиксу
  // обновляет и список, и сводку разом, поэтому после добавления расхода
  // их нельзя забыть развести.
  const summary = useQuery({
    queryKey: ["expenses", "summary"],
    queryFn: async () => (await api.GET("/api/expenses/summary")).data ?? [],
  })

  const totalMinor = (summary.data ?? []).reduce((sum, c) => sum + c.total_minor, 0)

  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { date: "", title: "", category: "Софт", amount: "" },
  })

  const create = useMutation({
    mutationFn: async (values: Values) => {
      const { error } = await api.POST("/api/expenses", { body: values })
      if (error) throw error
    },
    onSuccess: async () => {
      form.reset()
      await queryClient.invalidateQueries({ queryKey: ["expenses"] })
    },
    onError: (error) => {
      const parsed = toApiError(error)
      // Поле из конверта: сообщение встаёт под нужный ввод. Без field —
      // общим алертом, а не молча.
      if (parsed.field && parsed.field in form.getValues()) {
        form.setError(parsed.field as keyof Values, { message: parsed.message })
      } else {
        form.setError("root", { message: parsed.message })
      }
    },
  })

  const remove = useMutation({
    mutationFn: async (id: string) => {
      const { error } = await api.DELETE("/api/expenses/{expense_id}", {
        params: { path: { expense_id: id } },
      })
      if (error) throw error
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["expenses"] }),
  })

  return (
    <PageMain>
      <h1 className="text-3xl font-semibold">Расходы</h1>

      <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader>
            <CardDescription>Всего</CardDescription>
            {/* data-testid, а не поиск по тексту: сумма меняется от прогона
                к прогону, а по подписи «Всего» пришлось бы ходить к
                соседнему узлу через локатор-родитель — такой селектор
                ломается от любой правки вёрстки карточки. */}
            <CardTitle className="text-lg tabular-nums" data-testid="expenses-total">
              {formatMoney(totalMinor)}
            </CardTitle>
          </CardHeader>
        </Card>
        {summary.data?.map((c) => (
          <Card key={c.category}>
            <CardHeader>
              <CardDescription>{c.category}</CardDescription>
              <CardTitle className="text-lg tabular-nums">
                {formatMoney(c.total_minor)}
              </CardTitle>
              {/* Округление живёт здесь: сервер отдаёт точную долю.
                  Проценты округляются независимо друг от друга, поэтому
                  сложенные глазами могут дать не ровно 100 — это не ошибка
                  счёта, а цена показа целыми процентами. */}
              <CardDescription>{Math.round(c.share * 100)}%</CardDescription>
            </CardHeader>
          </Card>
        ))}
      </div>

      <Card className="mt-6">
        <CardHeader>
          <CardTitle>Новый расход</CardTitle>
        </CardHeader>
        <CardContent>
          <form
            className="grid gap-4 sm:grid-cols-4"
            onSubmit={form.handleSubmit((values) => create.mutate(values))}
          >
            <div className="space-y-2">
              <Label htmlFor="date">Дата</Label>
              <Input id="date" type="date" {...form.register("date")} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="title">Назначение</Label>
              <Input id="title" {...form.register("title")} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="category">Категория</Label>
              <Select
                value={form.watch("category")}
                onValueChange={(v) =>
                  form.setValue("category", v as Values["category"])
                }
              >
                <SelectTrigger id="category">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {/* Группа обязательна даже когда она одна: без обёртки
                      края пунктов прижимаются, и это выглядит как поехавшая
                      вёрстка, а не как забытый компонент. */}
                  <SelectGroup>
                    {CATEGORIES.map((c) => (
                      <SelectItem key={c} value={c}>
                        {c}
                      </SelectItem>
                    ))}
                  </SelectGroup>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="amount">Сумма</Label>
              <Input id="amount" inputMode="decimal" {...form.register("amount")} />
            </div>
            <div className="sm:col-span-4 space-y-3">
              {Object.values(form.formState.errors).map((error, index) => (
                <Alert key={index} variant="destructive">
                  <AlertDescription>{error?.message as string}</AlertDescription>
                </Alert>
              ))}
              <Button type="submit" disabled={create.isPending}>
                Добавить
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      <Table className="mt-8">
        <TableHeader>
          <TableRow>
            <TableHead>Дата</TableHead>
            <TableHead>Назначение</TableHead>
            <TableHead>Категория</TableHead>
            <TableHead className="text-right">Сумма</TableHead>
            <TableHead />
          </TableRow>
        </TableHeader>
        <TableBody>
          {expenses.data?.length === 0 && (
            // Пустое состояние обязательно: таблица из одних заголовков
            // читается как поломка, и на свежем контуре это первое, что
            // видит человек.
            <TableRow>
              <TableCell colSpan={5} className="text-muted-foreground py-8 text-center">
                Расходов пока нет. Добавь первый в форме выше.
              </TableCell>
            </TableRow>
          )}
          {expenses.data?.map((expense) => (
            <TableRow key={expense.id}>
              <TableCell>{formatDate(expense.date)}</TableCell>
              <TableCell>{expense.title}</TableCell>
              <TableCell>{expense.category}</TableCell>
              <TableCell className="text-right tabular-nums">
                {formatMoney(expense.amount_minor)}
              </TableCell>
              <TableCell className="text-right">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => remove.mutate(expense.id)}
                >
                  Удалить
                </Button>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </PageMain>
  )
}
