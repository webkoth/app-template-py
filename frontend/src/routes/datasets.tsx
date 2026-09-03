import { useState } from "react"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import {
  useMutation,
  useQuery,
  useQueryClient,
  useSuspenseQuery,
} from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"
import { z } from "zod"
import { api, toApiError, unwrap } from "@/api/client"
import type { components } from "@/api/schema"
import { PageMain } from "@/components/page-main"
import { RequestFailure } from "@/components/request-failure"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
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
import { currentUserQuery, hasRank } from "@/lib/auth"
import { formatDateTime } from "@/lib/format"

type Dataset = components["schemas"]["DatasetOut"]
type Model = components["schemas"]["ModelOut"]

// Вид числовой колонки. Слово задаёт `summarise` в
// backend/app/domain/tables.py, и здесь оно написано второй раз — контракт
// между разбором и показом держится на нём. Разъедется — числовые колонки
// перестанут находиться, и выбирать цель обучения будет не из чего.
const NUMERIC = "число"

/**
 * Сводка разбирается схемой, а не приводится типом.
 *
 * В схеме API сводка — это JSONB: «объект с неизвестными значениями», и
 * прочитать из него число нельзя, не сказав компилятору, что там лежит.
 * Приведение (`as`) сказало бы это молча, и первое же расхождение с
 * бэкендом уронило бы экран на отрисовке — «cannot read properties of
 * undefined» поверх всей страницы. safeParse превращает то же расхождение
 * в строку на экране, а остальные таблицы остаются видимыми.
 */
const SUMMARY = z.object({
  строк: z.number(),
  колонки: z.array(
    z.object({
      имя: z.string(),
      вид: z.string(),
      // nullish, а не number: у текстовой колонки этих полей нет вовсе, а
      // у числовой они приезжают пустыми, когда среднее не посчиталось
      // (колонка с ±inf даёт NaN, и бэкенд заменяет его на null).
      минимум: z.number().nullish(),
      максимум: z.number().nullish(),
      среднее: z.number().nullish(),
      различных: z.number().nullish(),
    })
  ),
})

const uploadSchema = z.object({
  // z.custom, а не z.instanceof(FileList): FileList существует только в
  // браузере, а z.instanceof читает глобаль в момент СОЗДАНИЯ схемы, то
  // есть при разборе модуля. Достаточно любого импорта этого файла вне
  // браузера, чтобы падал импорт, а не проверка.
  file: z.custom<FileList>(
    (value) =>
      typeof FileList !== "undefined" &&
      value instanceof FileList &&
      value.length > 0,
    "Выбери файл"
  ),
})

type UploadValues = z.infer<typeof uploadSchema>

const trainSchema = z.object({
  target_column: z.string().min(1, "Выбери колонку"),
})

type TrainValues = z.infer<typeof trainSchema>

// Имя метрики приезжает как «r2» — это идентификатор из sklearn, а не
// подпись человеку. Появится вторая метрика — строка заводится здесь.
const METRIC_LABEL: Record<string, string> = { r2: "R²" }

// Ключ ответа предсказания. В схеме это dict[str, float], имён полей она не
// знает, поэтому строка написана здесь второй раз.
const PREDICTION_KEY = "значение"

// Обновление, пока хоть одна таблица разбирается. Разбор идёт в фоне, и без
// опроса свежая таблица навсегда осталась бы «разбирается» — до того, как
// человек догадается перезагрузить страницу. Когда разбирать нечего, опрос
// не идёт вовсе: постоянный запрос ради неменяющегося списка греет контур
// задаром.
const POLL_MS = 3000

// Локаль задана явно и не по вкусу браузера — по той же причине, по которой
// деньги и даты форматирует lib/format.ts: число на экране не должно
// зависеть от настроек того, кто его открыл.
const NUMBER = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 4 })
const SIZE = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 1 })
const SIZE_UNITS = ["Б", "КиБ", "МиБ"]

/**
 * Размер файла человеку. В lib/format.ts не унесён намеренно: там живёт то,
 * что форматируют несколько экранов, а байты показывает только этот.
 */
function formatSize(bytes: number): string {
  let value = bytes
  let unit = 0
  while (value >= 1024 && unit < SIZE_UNITS.length - 1) {
    value /= 1024
    unit += 1
  }
  // Байты целым, остальное — с десятой долей: «1536 Б» не читается, а
  // «1,0 Б» — кокетство.
  return `${SIZE.format(unit === 0 ? Math.round(value) : value)} ${SIZE_UNITS[unit]}`
}

/** Разбор ещё идёт: сводки нет, но и причины, по которой её нет, тоже. */
function isParsing(dataset: Dataset): boolean {
  return dataset.summary === null && !dataset.parse_error
}

export function DatasetsPage() {
  const queryClient = useQueryClient()
  const { data: user } = useSuspenseQuery(currentUserQuery)
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const datasets = useQuery({
    queryKey: ["datasets"],
    // unwrap, а не `.data ?? []`: с запасным пустым массивом отказ стал бы
    // успешным пустым списком, и «таблиц пока нет» было бы неотличимо от
    // «нет доступа».
    queryFn: async () => unwrap(await api.GET("/api/datasets")),
    // Функцией от данных: разбор идёт в фоне, и пока он идёт, список
    // меняется сам по себе. Когда все таблицы разобраны — опрос
    // прекращается.
    refetchInterval: (query) =>
      query.state.data?.some(isParsing) ? POLL_MS : false,
  })

  const form = useForm<UploadValues>({ resolver: zodResolver(uploadSchema) })

  const upload = useMutation({
    mutationFn: async (values: UploadValues) => {
      const file = values.file[0]
      unwrap(
        await api.POST("/api/datasets", {
          // Приведение, а не ослабление типа: openapi-typescript отображает
          // binary в string, а File строкой не является. Само тело собирает
          // bodySerializer ниже.
          body: { file: file as unknown as string },
          // Маршрут принимает multipart/form-data. Без своего сериализатора
          // openapi-fetch отправил бы JSON.stringify(File) — то есть «{}», —
          // и бэкенд отказал бы «поле file обязательно», хотя файл выбран.
          // FormData он узнаёт сам и Content-Type с границей ставит браузер.
          bodySerializer: () => {
            const data = new FormData()
            data.append("file", file)
            return data
          },
        })
      )
    },
    onSuccess: async () => {
      form.reset()
      await queryClient.invalidateQueries({ queryKey: ["datasets"] })
    },
    onError: (error) => {
      const parsed = toApiError(error)
      // Поле из конверта: отказы загрузки (не CSV и не XLSX, больше
      // потолка) приезжают с field="file" и встают под своим вводом.
      if (parsed.field && parsed.field in form.getValues()) {
        form.setError(parsed.field as keyof UploadValues, {
          message: parsed.message,
        })
      } else {
        form.setError("root", { message: parsed.message })
      }
    },
  })

  // Гейт показа, и только показа: загрузку закрывает require_role(editor) на
  // бэкенде, и viewer, отправивший запрос руками, получит оттуда 403. Без
  // этой строки viewer видел бы форму загрузки, которой ему не
  // воспользоваться.
  //
  // Проверка на null формальная: без сессии сюда не пускает beforeLoad, но
  // тип currentUserQuery её допускает.
  const canWrite = user !== null && hasRank(user.role, "editor")

  // Выбранная таблица берётся из свежего списка, а не запоминается целиком:
  // список опрашивается, и сохранённая копия показывала бы «разбирается»
  // после того, как разбор закончился.
  const selected = datasets.data?.find((d) => d.id === selectedId) ?? null

  return (
    <PageMain>
      <h1 className="text-3xl font-semibold">Таблицы</h1>
      <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
        CSV или XLSX до 32 МиБ. Файл разбирается в фоне: строки и сводка
        появляются не сразу, а ход работы виден на экране «Задачи». По
        разобранной таблице можно обучить модель и сделать предсказание.
      </p>

      {canWrite && (
        <Card className="mt-6">
          <CardHeader>
            <CardTitle>Загрузить таблицу</CardTitle>
          </CardHeader>
          <CardContent>
            <form
              className="grid gap-4 sm:grid-cols-[1fr_auto]"
              onSubmit={form.handleSubmit((values) => upload.mutate(values))}
            >
              <div className="space-y-2">
                <Label htmlFor="file">Файл</Label>
                <Input
                  id="file"
                  type="file"
                  accept=".csv,.xlsx"
                  {...form.register("file")}
                />
                {/* Ошибка поля — под своим полем, общая — алертом ниже. Тот
                    же порядок, что на экранах расходов и людей. */}
                {form.formState.errors.file && (
                  <p className="text-sm text-destructive">
                    {form.formState.errors.file.message}
                  </p>
                )}
              </div>
              <div className="flex items-end">
                <Button type="submit" disabled={upload.isPending}>
                  Загрузить
                </Button>
              </div>
              {form.formState.errors.root && (
                <Alert variant="destructive" className="sm:col-span-2">
                  <AlertDescription>
                    {form.formState.errors.root.message}
                  </AlertDescription>
                </Alert>
              )}
            </form>
          </CardContent>
        </Card>
      )}

      {datasets.isError ? (
        <RequestFailure className="mt-8" error={datasets.error} />
      ) : (
        <Table className="mt-8">
          <TableHeader>
            <TableRow>
              <TableHead>Таблица</TableHead>
              <TableHead className="text-right">Размер</TableHead>
              <TableHead className="text-right">Строк</TableHead>
              <TableHead>Загружена</TableHead>
              <TableHead>Состояние</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {datasets.data?.length === 0 && (
              <TableRow>
                <TableCell
                  colSpan={5}
                  className="py-8 text-center text-muted-foreground"
                >
                  {canWrite
                    ? "Таблиц пока нет. Загрузи первую в форме выше."
                    : "Таблиц пока нет."}
                </TableCell>
              </TableRow>
            )}
            {datasets.data?.map((dataset) => (
              <TableRow
                key={dataset.id}
                data-state={dataset.id === selectedId ? "selected" : undefined}
                className="cursor-pointer"
                // Выбирается строка целиком, а не ссылка в первой ячейке:
                // сводка, модели и предсказание относятся ко всей строке.
                // tabIndex и обработчик клавиш обязательны — без них
                // выбрать таблицу с клавиатуры нельзя вовсе.
                tabIndex={0}
                onClick={() => setSelectedId(dataset.id)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault()
                    setSelectedId(dataset.id)
                  }
                }}
              >
                {/* original_name, а не name: в name бэкенд кладёт имя без
                    расширения, а человек ищет глазами тот файл, который
                    выбрал у себя на диске. */}
                <TableCell className="font-medium">
                  {dataset.original_name}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {formatSize(dataset.size_bytes)}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {/* Пока сводки нет, прочерк, а не 0: ноль здесь неотличим
                      от настоящего нуля строк, а «ещё не знаю» честнее. */}
                  {dataset.summary === null ? "—" : dataset.rows_count}
                </TableCell>
                <TableCell className="text-muted-foreground">
                  {formatDateTime(dataset.created_at)}
                </TableCell>
                <TableCell>
                  {/* Три разных состояния, а не два. Пустая сводка сама по
                      себе означает и «считаем», и «упало»: причина живёт в
                      задаче, и бэкенд приносит её сюда полем parse_error.
                      Есть причина — разбор не состоялся; нет причины и нет
                      сводки — работа идёт. */}
                  {dataset.parse_error ? (
                    <div className="space-y-1">
                      <Badge variant="destructive">не разобралась</Badge>
                      <div className="max-w-xs text-xs whitespace-normal text-destructive">
                        {dataset.parse_error}
                      </div>
                    </div>
                  ) : dataset.summary === null ? (
                    <Badge variant="secondary">разбирается</Badge>
                  ) : (
                    <Badge variant="outline">разобрана</Badge>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}

      {/* key — по таблице: при выборе другой строки карточка
          пересоздаётся, а вместе с ней сбрасываются выбранная цель
          обучения, выбранная модель и введённая строка для предсказания.
          Без этого форма предсказания осталась бы заполненной колонками
          прошлой таблицы.

          В ключе ещё и наличие сводки. Таблицу выбирают, пока она
          разбирается, — и в этот момент числовых колонок не знает никто, а
          форма обучения берёт из них своё начальное значение. Разбор
          заканчивается, список колонок появляется, но форма живёт с
          пустым выбором, и в ней стоит пустая строка вместо колонки.
          Пересборка карточки в момент появления сводки это и чинит. */}
      {selected !== null && (
        <DatasetDetails
          key={`${selected.id}:${selected.summary === null}`}
          dataset={selected}
          canWrite={canWrite}
        />
      )}
    </PageMain>
  )
}

/** Сводка выбранной таблицы, её модели и предсказание по ним. */
function DatasetDetails({
  dataset,
  canWrite,
}: {
  dataset: Dataset
  canWrite: boolean
}) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [modelId, setModelId] = useState<string | null>(null)

  const summary = SUMMARY.safeParse(dataset.summary)
  const columns = summary.success ? summary.data.колонки : []
  // Обучать можно только по числовой колонке: предсказывать «город» числом
  // нечем. Бэкенд это тоже проверяет и отказывает полем target_column —
  // здесь список сужен, чтобы не предлагать человеку заведомый отказ.
  const numeric = columns.filter((column) => column.вид === NUMERIC)

  const models = useQuery({
    queryKey: ["datasets", dataset.id, "models"],
    queryFn: async () =>
      unwrap(
        await api.GET("/api/datasets/{dataset_id}/models", {
          params: { path: { dataset_id: dataset.id } },
        })
      ),
  })

  const trainForm = useForm<TrainValues>({
    resolver: zodResolver(trainSchema),
    defaultValues: { target_column: numeric[0]?.имя ?? "" },
  })

  const train = useMutation({
    mutationFn: async (values: TrainValues) =>
      unwrap(
        await api.POST("/api/datasets/{dataset_id}/models", {
          params: { path: { dataset_id: dataset.id } },
          body: values,
        })
      ),
    onSuccess: async () => {
      // Ответ 202 означает «задача поставлена», а не «модель обучена»:
      // показывать здесь успех значило бы соврать про готовую модель.
      // Человека уводит туда, где видно ход работы и её отказ.
      await queryClient.invalidateQueries({ queryKey: ["jobs"] })
      await navigate({ to: "/jobs" })
    },
    onError: (error) => {
      const parsed = toApiError(error)
      if (parsed.field && parsed.field in trainForm.getValues()) {
        trainForm.setError(parsed.field as keyof TrainValues, {
          message: parsed.message,
        })
      } else {
        trainForm.setError("root", { message: parsed.message })
      }
    },
  })

  const model = models.data?.find((m) => m.id === modelId) ?? null

  return (
    <Card className="mt-8">
      <CardHeader>
        <CardTitle>{dataset.original_name}</CardTitle>
        <CardDescription>
          {summary.success
            ? `строк: ${summary.data.строк}`
            : dataset.parse_error
              ? "сводки нет — разбор не состоялся"
              : "сводка считается"}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-8">
        {dataset.parse_error && (
          <Alert variant="destructive">
            <AlertTitle>Разбор не состоялся</AlertTitle>
            <AlertDescription>{dataset.parse_error}</AlertDescription>
          </Alert>
        )}

        {!summary.success && !dataset.parse_error && (
          <p className="text-sm text-muted-foreground">
            Таблица разбирается в фоне. Сводка появится здесь сама — экран
            обновляется, пока работа идёт.
          </p>
        )}

        {summary.success && (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Колонка</TableHead>
                <TableHead>Вид</TableHead>
                <TableHead className="text-right">Минимум</TableHead>
                <TableHead className="text-right">Максимум</TableHead>
                <TableHead className="text-right">Среднее</TableHead>
                <TableHead className="text-right">Различных</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {columns.map((column) => (
                <TableRow key={column.имя}>
                  <TableCell className="font-medium">{column.имя}</TableCell>
                  <TableCell className="text-muted-foreground">
                    {column.вид}
                  </TableCell>
                  {/* Числа только у числовых колонок, у остальных —
                      прочерк. Пустая ячейка читалась бы как «ноль». */}
                  <TableCell className="text-right tabular-nums">
                    {formatCell(column.минимум)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {formatCell(column.максимум)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {formatCell(column.среднее)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {formatCell(column.различных)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}

        {/* Форма обучения — только editor и выше, и это показ: обучение
            закрыто на бэкенде require_role(editor). */}
        {canWrite && summary.success && (
          <form
            className="grid gap-4 sm:grid-cols-[1fr_auto]"
            onSubmit={trainForm.handleSubmit((values) => train.mutate(values))}
          >
            <div className="space-y-2">
              <Label htmlFor="target">Целевая колонка</Label>
              {numeric.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  В таблице нет числовых колонок — предсказывать нечего.
                </p>
              ) : (
                <Select
                  value={trainForm.watch("target_column")}
                  onValueChange={(value) =>
                    trainForm.setValue("target_column", value as string)
                  }
                >
                  {/* items здесь не нужен, в отличие от списка ролей:
                      значение и подпись — это одно и то же имя колонки, и
                      SelectValue печатает само значение. */}
                  <SelectTrigger id="target" className="w-64">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectGroup>
                      {numeric.map((column) => (
                        <SelectItem key={column.имя} value={column.имя}>
                          {column.имя}
                        </SelectItem>
                      ))}
                    </SelectGroup>
                  </SelectContent>
                </Select>
              )}
              {trainForm.formState.errors.target_column && (
                <p className="text-sm text-destructive">
                  {trainForm.formState.errors.target_column.message}
                </p>
              )}
            </div>
            <div className="flex items-end">
              <Button
                type="submit"
                disabled={train.isPending || numeric.length === 0}
              >
                Обучить модель
              </Button>
            </div>
            {trainForm.formState.errors.root && (
              <Alert variant="destructive" className="sm:col-span-2">
                <AlertDescription>
                  {trainForm.formState.errors.root.message}
                </AlertDescription>
              </Alert>
            )}
          </form>
        )}

        <div className="space-y-4">
          <h2 className="text-lg font-medium">Обученные модели</h2>
          {models.isError ? (
            <RequestFailure error={models.error} />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Обучена</TableHead>
                  <TableHead>Цель</TableHead>
                  <TableHead>Признаки</TableHead>
                  <TableHead>Метрика</TableHead>
                  <TableHead>Кто</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {models.data?.length === 0 && (
                  <TableRow>
                    <TableCell
                      colSpan={6}
                      className="py-8 text-center text-muted-foreground"
                    >
                      Моделей пока нет. Обучение идёт в фоне: поставленная
                      задача видна на экране «Задачи».
                    </TableCell>
                  </TableRow>
                )}
                {models.data?.map((item) => (
                  <TableRow
                    key={item.id}
                    data-state={item.id === modelId ? "selected" : undefined}
                  >
                    <TableCell className="text-muted-foreground">
                      {formatDateTime(item.created_at)}
                    </TableCell>
                    <TableCell className="font-medium">
                      {item.target_column}
                    </TableCell>
                    <TableCell className="max-w-xs whitespace-normal">
                      {item.feature_columns.join(", ")}
                    </TableCell>
                    <TableCell className="tabular-nums">
                      {METRIC_LABEL[item.metric_name] ?? item.metric_name}{" "}
                      {NUMBER.format(item.metric_value)}
                    </TableCell>
                    <TableCell>{item.actor}</TableCell>
                    <TableCell className="text-right">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setModelId(item.id)}
                      >
                        Предсказать
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
          {/* key — по модели: у другой модели другие колонки, и введённые
              значения от прошлой к ним не относятся. */}
          {model !== null && <PredictForm key={model.id} model={model} />}
        </div>
      </CardContent>
    </Card>
  )
}

/** Число из сводки или прочерк: у текстовой колонки этих полей нет. */
function formatCell(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : NUMBER.format(value)
}

/**
 * Предсказание по обученной модели. Идёт сразу, без очереди: обучение
 * долгое, предсказание — миллисекунды.
 *
 * Форма собрана на состоянии, а не на react-hook-form, в отличие от
 * остальных форм проекта: имена полей здесь приходят из данных, а
 * react-hook-form разбирает имя поля как путь — колонка «цена.руб» стала бы
 * вложенным объектом и уехала бы в тело запроса не тем ключом.
 */
function PredictForm({ model }: { model: Model }) {
  const [row, setRow] = useState<Record<string, string>>({})
  const [missing, setMissing] = useState<string[]>([])

  const predict = useMutation({
    mutationFn: async (values: Record<string, number>) =>
      unwrap(
        await api.POST("/api/models/{model_id}/predict", {
          params: { path: { model_id: model.id } },
          body: { row: values },
        })
      ),
  })

  const value = predict.data?.[PREDICTION_KEY]

  return (
    <form
      className="space-y-4 rounded-lg border border-border p-4"
      onSubmit={(event) => {
        event.preventDefault()
        // Number("") — это 0, и пустое поле уехало бы на сервер нулём:
        // сервер честно вернул бы предсказание по нулю, а число на экране
        // было бы тихо неверным. Браузер до этого не доводит (required и
        // type=number), проверка здесь — вторая линия.
        const empty = model.feature_columns.filter(
          (column) => (row[column] ?? "").trim() === ""
        )
        setMissing(empty)
        if (empty.length > 0) return
        const values: Record<string, number> = {}
        // Порядок колонок задаёт модель, а не форма: артефакт обучен на
        // этом порядке, и он же собирает строку на бэкенде.
        for (const column of model.feature_columns) {
          values[column] = Number(row[column])
        }
        predict.mutate(values)
      }}
    >
      <h3 className="font-medium">
        Предсказать «{model.target_column}» по строке
      </h3>
      <div className="grid gap-4 sm:grid-cols-3">
        {model.feature_columns.map((column, index) => (
          <div key={column} className="space-y-2">
            <Label htmlFor={`predict-${model.id}-${index}`}>{column}</Label>
            <Input
              id={`predict-${model.id}-${index}`}
              type="number"
              step="any"
              required
              value={row[column] ?? ""}
              onChange={(event) =>
                setRow({ ...row, [column]: event.target.value })
              }
            />
          </div>
        ))}
      </div>
      {missing.length > 0 && (
        <Alert variant="destructive">
          <AlertDescription>
            Заполни колонки: {missing.join(", ")}
          </AlertDescription>
        </Alert>
      )}
      {predict.isError && (
        <RequestFailure
          title="Предсказание не получилось"
          error={predict.error}
        />
      )}
      <div className="flex items-center gap-4">
        <Button type="submit" disabled={predict.isPending}>
          Предсказать
        </Button>
        {typeof value === "number" && (
          <p className="text-sm">
            {model.target_column}:{" "}
            <span className="font-medium tabular-nums">
              {NUMBER.format(value)}
            </span>
          </p>
        )}
      </div>
    </form>
  )
}
