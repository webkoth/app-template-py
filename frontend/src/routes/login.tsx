import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"
import { z } from "zod"
import { api, toApiError } from "@/api/client"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

const schema = z.object({
  login: z.string().min(1, "Укажи логин"),
  password: z.string().min(1, "Укажи пароль"),
})

type Values = z.infer<typeof schema>

export function LoginPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { login: "", password: "" },
  })

  const submit = useMutation({
    mutationFn: async (values: Values) => {
      const { error } = await api.POST("/api/auth/login", { body: values })
      if (error) throw error
    },
    onSuccess: async () => {
      // refetchQueries, а не invalidateQueries. invalidate перезапрашивает
      // только активные запросы, а на форме входа за currentUserQuery никто
      // не подписан: запрос помечался бы устаревшим, но в кэше оставался бы
      // null — тот самый, который положил гейт, уводя сюда. ensureQueryData
      // в beforeLoad отдаёт кэш как есть (null — это данные, а не пустота),
      // видит «не вошёл» и возвращает на /login. Замерено в браузере: с
      // invalidate верная пара admin / admin оставляла на форме входа
      // молча, без ошибки, а перезагрузка страницы открывала главную.
      await queryClient.refetchQueries({ queryKey: ["auth", "me"] })
      await navigate({ to: "/" })
    },
    onError: (error) => {
      const parsed = toApiError(error)
      // Ошибка входа всегда общая: бэкенд намеренно не говорит, логин
      // неверен или пароль, — и раскладывать её по полям нечего.
      form.setError("root", { message: parsed.message })
    },
  })

  return (
    <div className="flex min-h-svh items-center justify-center px-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>Вход</CardTitle>
        </CardHeader>
        <CardContent>
          <form
            className="space-y-4"
            onSubmit={form.handleSubmit((values) => submit.mutate(values))}
          >
            <div className="space-y-2">
              <Label htmlFor="login">Логин</Label>
              <Input id="login" autoComplete="username" {...form.register("login")} />
              {form.formState.errors.login && (
                <p className="text-destructive text-sm">
                  {form.formState.errors.login.message}
                </p>
              )}
            </div>
            <div className="space-y-2">
              <Label htmlFor="password">Пароль</Label>
              <Input
                id="password"
                type="password"
                autoComplete="current-password"
                {...form.register("password")}
              />
              {form.formState.errors.password && (
                <p className="text-destructive text-sm">
                  {form.formState.errors.password.message}
                </p>
              )}
            </div>
            {form.formState.errors.root && (
              <Alert variant="destructive">
                <AlertDescription>
                  {form.formState.errors.root.message}
                </AlertDescription>
              </Alert>
            )}
            <Button type="submit" className="w-full" disabled={submit.isPending}>
              {submit.isPending ? "Проверяю…" : "Войти"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
