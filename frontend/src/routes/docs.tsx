import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { api, unwrap } from "@/api/client"
import { MarkdownView } from "@/components/markdown-view"
import { PageMain } from "@/components/page-main"
import { RequestFailure } from "@/components/request-failure"
import { Skeleton } from "@/components/ui/skeleton"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"

// Имена — те же, что в разрешённом списке бэкенда (DOCUMENTS в
// features/meta/router.py). Сверять их глазами не нужно: имя уезжает в путь
// запроса, а тип пути сгенерирован из схемы. Проверено зондом — строка
// { name: "выдуманное" } в этом списке роняет tsc на вызове api.GET.
const DOCUMENTS = [
  { name: "agents", label: "Правила" },
  { name: "checklist", label: "Что умеет" },
  { name: "onboarding", label: "Установка" },
  { name: "ship", label: "Доставка" },
  { name: "status", label: "Состояние" },
  { name: "logs", label: "Логи" },
  { name: "rollback", label: "Откат" },
] as const

type DocumentName = (typeof DOCUMENTS)[number]["name"]

export function DocsPage() {
  const [current, setCurrent] = useState<DocumentName>("agents")

  // Переменная зовётся doc, а не document: имя document занято глобальным
  // объектом страницы, и внутри компонента оно бы его перекрыло — код,
  // который дальше захочет настоящий document, молча получит ответ запроса.
  const doc = useQuery({
    queryKey: ["docs", current],
    // unwrap, а не `.data ?? null`: отказ иначе неотличим от пустого
    // документа. Документы тут не косметика — это правила, по которым
    // пишут код, и «правил нет» вместо «сервер не отдал» читается как
    // разрешение.
    queryFn: async () =>
      unwrap(
        await api.GET("/api/meta/docs/{name}", {
          params: { path: { name: current } },
        })
      ),
  })

  return (
    <PageMain>
      <h1 className="text-3xl font-semibold">Правила и команды</h1>
      <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
        Файлы репозитория, прочитанные с диска: те же самые, что читает агент.
        Это не копия и не пересказ — расходиться им негде.
      </p>
      {/* overflow-x-auto: семь вкладок в строку не помещаются на узком
          экране, и без прокрутки последние («Логи», «Откат») оказывались за
          краем страницы — нажать их было нечем. overflow-y-hidden рядом
          обязателен: браузер, увидев прокрутку по одной оси, включает
          автоматическую и по второй, и рядом с полосой прокрутки внизу
          появлялась ещё одна, вертикальная, на высоту в один пиксель. */}
      <Tabs
        value={current}
        onValueChange={(v) => setCurrent(v as DocumentName)}
        className="mt-6 overflow-x-auto overflow-y-hidden"
      >
        <TabsList>
          {DOCUMENTS.map((item) => (
            <TabsTrigger key={item.name} value={item.name}>
              {item.label}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>
      <div className="mt-8">
        {doc.isPending ? (
          <div className="space-y-3">
            <Skeleton className="h-4 w-2/3" />
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-5/6" />
          </div>
        ) : doc.isError ? (
          <RequestFailure error={doc.error} />
        ) : (
          <MarkdownView content={doc.data.content} />
        )}
      </div>
    </PageMain>
  )
}
