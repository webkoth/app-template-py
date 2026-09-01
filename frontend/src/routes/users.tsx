import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import {
  useMutation,
  useQuery,
  useQueryClient,
  useSuspenseQuery,
} from "@tanstack/react-query"
import { z } from "zod"
import { api, toApiError, unwrap } from "@/api/client"
import { PageMain } from "@/components/page-main"
import { RequestFailure } from "@/components/request-failure"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
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
import { currentUserQuery, hasRank } from "@/lib/auth"
import { formatDateTime } from "@/lib/format"

const ROLES = ["viewer", "editor", "admin"] as const
const ROLE_LABEL: Record<(typeof ROLES)[number], string> = {
  viewer: "Смотрит",
  editor: "Правит",
  admin: "Управляет",
}

const schema = z.object({
  login: z.string().min(1, "Укажи логин").regex(/^\S+$/, "Логин без пробелов"),
  name: z.string().min(1, "Укажи имя"),
  role: z.enum(ROLES),
  password: z.string().min(8, "Не короче восьми символов"),
})

type Values = z.infer<typeof schema>

export function UsersPage() {
  const queryClient = useQueryClient()
  const { data: currentUser } = useSuspenseQuery(currentUserQuery)

  const users = useQuery({
    queryKey: ["users"],
    // unwrap, а не `.data ?? []`: с запасным пустым массивом отказ
    // становился успешным пустым списком, и viewer по прямой ссылке на
    // /users читал «Учётных записей пока нет» — при том что пришёл 403.
    queryFn: async () => unwrap(await api.GET("/api/users")),
  })

  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { login: "", name: "", role: "viewer", password: "" },
  })

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["users"] })

  const create = useMutation({
    mutationFn: async (values: Values) => {
      unwrap(await api.POST("/api/users", { body: values }))
    },
    onSuccess: async () => {
      form.reset()
      await invalidate()
    },
    onError: (error) => {
      const parsed = toApiError(error)
      if (parsed.field && parsed.field in form.getValues()) {
        form.setError(parsed.field as keyof Values, { message: parsed.message })
      } else {
        form.setError("root", { message: parsed.message })
      }
    },
  })

  const update = useMutation({
    mutationFn: async (input: {
      id: string
      role?: (typeof ROLES)[number]
      status?: "active" | "disabled"
    }) => {
      unwrap(
        await api.PATCH("/api/users/{user_id}", {
          params: { path: { user_id: input.id } },
          body: { role: input.role ?? null, status: input.status ?? null },
        })
      )
    },
    onSuccess: invalidate,
  })

  // Гейт показа, и только показа: список, заведение и правка ролей закрыты
  // на бэкенде через require_role(admin), и viewer, отправивший запрос
  // руками, получит оттуда 403. Без этой строки viewer по прямой ссылке
  // видел форму заведения учётной записи, которой ему всё равно не
  // воспользоваться.
  //
  // Проверка на null формальная: без сессии сюда не пускает beforeLoad.
  const canManage = currentUser !== null && hasRank(currentUser.role, "admin")

  return (
    <PageMain>
      <h1 className="text-3xl font-semibold">Люди</h1>
      <p className="text-muted-foreground mt-2 max-w-2xl text-sm">
        Учётные записи не удаляются: удалённый автор записи в журнале
        превратил бы историю в набор осиротевших строк. Вместо удаления —
        отключение: вход закрывается, уже выданные сессии отзываются.
      </p>

      {canManage && (
        <Card className="mt-6">
          <CardHeader>
            <CardTitle>Новая учётная запись</CardTitle>
          </CardHeader>
          <CardContent>
            <form
              className="grid gap-4 sm:grid-cols-4"
              onSubmit={form.handleSubmit((values) => create.mutate(values))}
            >
              {/* Ошибка поля — под своим полем, общая — алертом внизу. Тот
                  же порядок, что на экране расходов: список алертов под
                  формой не показывал, к какому вводу относится «Не короче
                  восьми символов». */}
              <div className="space-y-2">
                <Label htmlFor="login">Логин</Label>
                <Input id="login" {...form.register("login")} />
                {form.formState.errors.login && (
                  <p className="text-destructive text-sm">
                    {form.formState.errors.login.message}
                  </p>
                )}
              </div>
              <div className="space-y-2">
                <Label htmlFor="name">Имя</Label>
                <Input id="name" {...form.register("name")} />
                {form.formState.errors.name && (
                  <p className="text-destructive text-sm">
                    {form.formState.errors.name.message}
                  </p>
                )}
              </div>
              <div className="space-y-2">
                <Label htmlFor="role">Роль</Label>
                <Select
                  // items обязателен: Select здесь из Base UI, и его
                  // SelectValue без этой карты печатает в кнопке само
                  // значение — «viewer» вместо «Смотрит». Найдено глазами:
                  // ROLE_LABEL применялся только к пунктам списка, а
                  // закрытая кнопка показывала английское значение из базы.
                  items={ROLE_LABEL}
                  value={form.watch("role")}
                  onValueChange={(v) => form.setValue("role", v as Values["role"])}
                >
                  <SelectTrigger id="role">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectGroup>
                      {ROLES.map((role) => (
                        <SelectItem key={role} value={role}>
                          {ROLE_LABEL[role]}
                        </SelectItem>
                      ))}
                    </SelectGroup>
                  </SelectContent>
                </Select>
                {form.formState.errors.role && (
                  <p className="text-destructive text-sm">
                    {form.formState.errors.role.message}
                  </p>
                )}
              </div>
              <div className="space-y-2">
                <Label htmlFor="password">Пароль</Label>
                <Input id="password" type="password" {...form.register("password")} />
                {form.formState.errors.password && (
                  <p className="text-destructive text-sm">
                    {form.formState.errors.password.message}
                  </p>
                )}
              </div>
              <div className="sm:col-span-4 space-y-3">
                {form.formState.errors.root && (
                  <Alert variant="destructive">
                    <AlertDescription>
                      {form.formState.errors.root.message}
                    </AlertDescription>
                  </Alert>
                )}
                <Button type="submit" disabled={create.isPending}>
                  Завести
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      )}

      {/* Отказ правки — из состояния мутации, без onError: react-query
          держит ошибку сам и сбрасывает её на следующей попытке. Смена
          роли и отключение доступа отвечали 403 или обрывом связи молча,
          и Select возвращался к прежнему значению без объяснения. */}
      {update.isError && (
        <RequestFailure
          className="mt-8"
          title="Изменение не сохранено"
          error={update.error}
        />
      )}

      {users.isError ? (
        <RequestFailure className="mt-8" error={users.error} />
      ) : (
        <Table className="mt-8">
          <TableHeader>
            <TableRow>
              <TableHead>Логин</TableHead>
              <TableHead>Имя</TableHead>
              <TableHead>Роль</TableHead>
              <TableHead>Последний вход</TableHead>
              <TableHead className="text-right">Доступ</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {users.data?.length === 0 && (
              <TableRow>
                <TableCell
                  colSpan={5}
                  className="text-muted-foreground py-8 text-center"
                >
                  Учётных записей пока нет.
                </TableCell>
              </TableRow>
            )}
            {users.data?.map((user) => (
              <TableRow key={user.id}>
                <TableCell className="font-medium">{user.login}</TableCell>
                <TableCell>{user.name}</TableCell>
                <TableCell>
                  <Select
                    // items — та же карта подписей, что и в форме выше: без
                    // неё в строке таблицы стоит «viewer», а не «Смотрит».
                    items={ROLE_LABEL}
                    // key привязан к значению: без него после обновления
                    // списка строка не размонтируется, и Select показывает
                    // старую роль при изменившихся данных.
                    key={`${user.id}-${user.role}`}
                    value={user.role}
                    onValueChange={(role) =>
                      update.mutate({
                        id: user.id,
                        role: role as (typeof ROLES)[number],
                      })
                    }
                  >
                    <SelectTrigger className="w-36">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectGroup>
                        {ROLES.map((role) => (
                          <SelectItem key={role} value={role}>
                            {ROLE_LABEL[role]}
                          </SelectItem>
                        ))}
                      </SelectGroup>
                    </SelectContent>
                  </Select>
                </TableCell>
                <TableCell className="text-muted-foreground">
                  {user.last_login_at
                    ? formatDateTime(user.last_login_at)
                    : "не входил"}
                </TableCell>
                <TableCell className="text-right">
                  {user.status === "active" ? (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => update.mutate({ id: user.id, status: "disabled" })}
                    >
                      Отключить
                    </Button>
                  ) : (
                    <div className="flex items-center justify-end gap-2">
                      <Badge variant="secondary">отключена</Badge>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => update.mutate({ id: user.id, status: "active" })}
                      >
                        Включить
                      </Button>
                    </div>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </PageMain>
  )
}
