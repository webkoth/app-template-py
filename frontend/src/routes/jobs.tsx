import { useEffect, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { api, unwrap } from "@/api/client"
import type { components } from "@/api/schema"
import { PageMain } from "@/components/page-main"
import { RequestFailure } from "@/components/request-failure"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Progress, ProgressValue } from "@/components/ui/progress"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { formatDateTime } from "@/lib/format"

type Job = components["schemas"]["JobOut"]

// Подписи состояний — по той же причине, что и подписи действий в журнале:
// на экран смотрит владелец бизнеса, а в колонке стояло бы «queued» и
// «failed» — значения перечисления с бэкенда, написанные для программиста.
// Ключи — ровно значения JobStatus из backend/app/core/jobs.py.
const STATUS_LABEL: Record<string, string> = {
  queued: "в очереди",
  running: "выполняется",
  done: "готово",
  failed: "не удалась",
}

const STATUS_VARIANT: Record<string, "default" | "secondary" | "destructive"> =
  {
    queued: "secondary",
    running: "default",
    done: "secondary",
    failed: "destructive",
  }

// Вид задачи — ключ реестра обработчиков (PARSE и TRAIN в
// backend/app/features/datasets/jobs.py). Появится новый вид — строка
// заводится здесь, иначе на экране стоит «datasets.parse».
const KIND_LABEL: Record<string, string> = {
  "datasets.parse": "разбор таблицы",
  "datasets.train": "обучение модели",
}

// Ключ ответа /api/jobs/health. В схеме это dict[str, bool], имён полей она
// не знает, поэтому строка написана здесь второй раз. Разъедется с
// бэкендом — признак станет undefined, и предупреждение ниже пропадёт
// молча: показывается оно только на явном false.
const WORKER_ALIVE = "воркер_жив"

// Незавершённые задачи. Отказавшая задача возвращается в очередь, пока не
// исчерпаны попытки, поэтому «queued» встречается и с непустой причиной —
// это «упало, будет повтор», а не «ещё не начинали».
const UNFINISHED = new Set(["queued", "running"])

// Обновление, пока на экране есть незавершённые задачи. Постоянный опрос
// ради неменяющейся таблицы греет контур задаром: очередь без работы не
// меняется вовсе.
const POLL_MS = 3000

// Сколько держать сомнение при себе, прежде чем сказать «некому взять».
//
// Признак живости неточен сразу после постановки задачи: воркер опрашивает
// очередь раз в JOB_POLL_SECONDS (по умолчанию секунда), и до тех пор
// свежей отметки живости нет ни у одной задачи — /api/jobs/health честно
// отвечает «не жив» на исправном контуре. Без выдержки предупреждение
// вспыхивало бы при каждой загрузке файла, а мигающее предупреждение
// перестают читать вместе с настоящими.
//
// Восемь секунд — это больше двух оборотов опроса экрана и много больше
// оборота воркера. Цена — настоящий мёртвый воркер объявляется на восемь
// секунд позже; ложная тревога не показывается вообще.
const STALL_GRACE_MS = 8000

export function JobsPage() {
  const jobs = useQuery({
    queryKey: ["jobs"],
    // unwrap, а не `.data ?? []`: с запасным пустым массивом отказ стал бы
    // успешным пустым списком, и «задач нет» было бы неотличимо от «нет
    // доступа». Отказ показывает RequestFailure ниже.
    queryFn: async () => unwrap(await api.GET("/api/jobs")),
    // Функцией от данных, а не числом: очередь без незавершённых задач не
    // меняется, и опрашивать её незачем.
    refetchInterval: (query) =>
      query.state.data?.some((job) => UNFINISHED.has(job.status))
        ? POLL_MS
        : false,
  })

  // Пока список не пришёл — считаем, что незавершённых нет: предупреждать
  // не о чем, а сам отказ показывает RequestFailure. Это не `?? []` вместо
  // данных: таблица ниже рисуется из jobs.data, а не из этого числа.
  const unfinished =
    jobs.data?.filter((job) => UNFINISHED.has(job.status)).length ?? 0

  const datasets = useQuery({
    queryKey: ["datasets"],
    queryFn: async () => unwrap(await api.GET("/api/datasets")),
    // Опрашивается вместе с задачами и по той же причине: таблицу
    // загрузили секунду назад, и без обновления её задача стояла бы с
    // идентификатором вместо имени.
    refetchInterval: unfinished > 0 ? POLL_MS : false,
  })

  const health = useQuery({
    // Ключ вложен в ["jobs"]: invalidateQueries по этому префиксу обновляет
    // и список, и признак живости разом — например когда экран таблиц
    // поставил обучение.
    queryKey: ["jobs", "health"],
    queryFn: async () => unwrap(await api.GET("/api/jobs/health")),
    refetchInterval: unfinished > 0 ? POLL_MS : false,
  })

  // Имя таблицы вместо её идентификатора. Отказ этого запроса экран не
  // прячет и пустотой не подменяет: в колонке останется идентификатор — он
  // приехал вместе с задачей и никуда не делся. Своего RequestFailure тут
  // нет намеренно: главные данные экрана — задачи, и ронять их показ из-за
  // подписи было бы хуже, чем показать подпись сырой.
  // original_name, а не name: в name бэкенд кладёт имя без расширения, а
  // человек ищет глазами тот файл, который выбрал у себя на диске, — и на
  // экране таблиц стоит тоже original_name.
  const datasetNames = new Map(
    datasets.data?.map(
      (dataset) => [dataset.id, dataset.original_name] as const
    )
  )

  // Сомнение: работа в очереди есть, а признака живости нет ни у одной
  // задачи. Само по себе это ещё не значит «воркера нет» — см. выдержку.
  const suspicious = unfinished > 0 && health.data?.[WORKER_ALIVE] === false
  const [stalled, setStalled] = useState(false)

  useEffect(() => {
    // Выдержка отмеряется от появления сомнения, а не от оборота опроса:
    // ответ /api/jobs/health не меняется, react-query отдаёт тот же объект,
    // и перерисовки по таймеру одного лишь запроса не случилось бы вовсе.
    if (!suspicious) return
    const timer = setTimeout(() => setStalled(true), STALL_GRACE_MS)
    return () => {
      clearTimeout(timer)
      // Сомнение исчезло — забывается и то, что оно держалось. Без этого
      // следующая поставленная задача зажигала бы предупреждение мгновенно
      // и без выдержки: воркер её ещё не взял, признака живости нет, а
      // «уже держалось восемь секунд» осталось с прошлого раза.
      setStalled(false)
    }
  }, [suspicious])

  return (
    <PageMain>
      <h1 className="text-3xl font-semibold">Задачи</h1>
      <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
        Долгая работа идёт в фоне: разбор загруженной таблицы и обучение модели.
        Свои задачи видит каждый, все — администратор. Пока есть незавершённые,
        экран обновляется сам.
      </p>

      {stalled && (
        <Alert variant="destructive" className="mt-6">
          {/* «В очереди» и «некому взять» выглядят на экране одинаково, и
              без этой строки человек ждёт результата, которого не будет.
              Признак — /api/jobs/health: свежая отметка живости хотя бы у
              одной задачи. */}
          <AlertTitle>Задачи некому взять</AlertTitle>
          <AlertDescription>
            Незавершённые задачи есть, а воркер не подаёт признаков жизни:
            свежей отметки нет ни у одной задачи. Это не медленный счёт — пока
            процесс воркера не поднимут, задача так и останется «в очереди». На
            контуре воркер — второй процесс pm2,{" "}
            <code>&lt;слаг&gt;-worker</code>; на своей машине —{" "}
            <code>{"cd backend && uv run python -m app.worker"}</code>.
          </AlertDescription>
        </Alert>
      )}

      {jobs.isError ? (
        <RequestFailure className="mt-6" error={jobs.error} />
      ) : (
        <Table className="mt-6">
          <TableHeader>
            <TableRow>
              <TableHead>Вид</TableHead>
              <TableHead>Таблица</TableHead>
              <TableHead>Состояние</TableHead>
              <TableHead>Прогресс</TableHead>
              <TableHead>Кто поставил</TableHead>
              <TableHead>Создана</TableHead>
              <TableHead>Завершена</TableHead>
              <TableHead>Причина отказа</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {jobs.data?.length === 0 && (
              <TableRow>
                <TableCell
                  colSpan={8}
                  className="py-8 text-center text-muted-foreground"
                >
                  Задач пока нет — они появляются при загрузке таблицы и при
                  обучении модели.
                </TableCell>
              </TableRow>
            )}
            {jobs.data?.map((job) => (
              <TableRow key={job.id}>
                <TableCell>{KIND_LABEL[job.kind] ?? job.kind}</TableCell>
                <TableCell>
                  <JobSubject job={job} names={datasetNames} />
                </TableCell>
                <TableCell>
                  <Badge variant={STATUS_VARIANT[job.status] ?? "secondary"}>
                    {STATUS_LABEL[job.status] ?? job.status}
                  </Badge>
                  {job.attempts > 1 && (
                    // Число попыток видно только когда их было больше
                    // одной, и тогда оно объясняет непустую причину у
                    // задачи, которая снова стоит в очереди: очередь
                    // возвращает отказавшую задачу, пока попытки не
                    // исчерпаны.
                    <div className="mt-1 text-xs text-muted-foreground">
                      попыток: {job.attempts}
                    </div>
                  )}
                </TableCell>
                <TableCell>
                  {UNFINISHED.has(job.status) ? (
                    // Полоса — только у незавершённых. У сотни строк
                    // истории она превращается в шум, а у отказавшей задачи
                    // важно не «сколько осталось», а на чём остановились —
                    // и это говорит число.
                    <Progress
                      value={job.progress}
                      locale="ru-RU"
                      className="w-24"
                    >
                      <ProgressValue />
                    </Progress>
                  ) : (
                    <span className="text-muted-foreground tabular-nums">
                      {job.progress} %
                    </span>
                  )}
                </TableCell>
                <TableCell>{job.actor}</TableCell>
                <TableCell className="text-muted-foreground">
                  {formatDateTime(job.created_at)}
                </TableCell>
                <TableCell className="text-muted-foreground">
                  {job.finished_at ? formatDateTime(job.finished_at) : "—"}
                </TableCell>
                <TableCell className="max-w-xs whitespace-normal text-destructive">
                  {/* Причина живёт только здесь и в серверном логе.
                      Пустая строка — не отказ: у задачи, которая идёт или
                      прошла, причины нет. */}
                  {job.error || (
                    <span className="text-muted-foreground">—</span>
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

/**
 * Над чем задача работает. Читается из payload — того самого поля, ради
 * которого оно и заведено: десять строк «разбор таблицы» без него
 * неразличимы, и понять, КАКАЯ таблица не разобралась, нельзя ни по чему.
 *
 * Имя берётся из списка таблиц, а идентификатор остаётся запасным ответом:
 * таблицу могли удалить, пока задача ждала, или список ещё не приехал.
 * Пустая ячейка вместо этого означала бы «задача ни над чем не работает».
 */
function JobSubject({ job, names }: { job: Job; names: Map<string, string> }) {
  // typeof, а не приведение: payload — это JSONB, и схема знает о нём
  // только «объект с неизвестными значениями». Кладёт туда значения фича,
  // ставящая задачу, и вид у нового вида задач будет другой.
  const datasetId =
    typeof job.payload["dataset_id"] === "string"
      ? job.payload["dataset_id"]
      : null
  const target =
    typeof job.payload["target_column"] === "string"
      ? job.payload["target_column"]
      : null

  if (datasetId === null) {
    return <span className="text-muted-foreground">—</span>
  }

  const name = names.get(datasetId)
  return (
    <div>
      {name === undefined ? (
        <span className="font-mono text-xs text-muted-foreground">
          {datasetId}
        </span>
      ) : (
        <span>{name}</span>
      )}
      {target !== null && (
        <div className="text-xs text-muted-foreground">цель: {target}</div>
      )}
    </div>
  )
}
