import {
  Card,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  Avatar,
  AvatarBadge,
  AvatarFallback,
  AvatarGroup,
} from "@/components/ui/avatar"
import {
  Progress,
  ProgressLabel,
  ProgressValue,
} from "@/components/ui/progress"
import { Separator } from "@/components/ui/separator"
import { Skeleton } from "@/components/ui/skeleton"
import { Group, Section } from "./showcase-section"

const ROWS = [
  {
    date: "28.08.2026",
    title: "Подписка на трекер",
    category: "Софт",
    sum: "2 490,00 ₽",
  },
  {
    date: "21.08.2026",
    title: "Монитор",
    category: "Оборудование",
    sum: "31 990,00 ₽",
  },
  {
    date: "14.08.2026",
    title: "Курьерская доставка",
    category: "Прочее",
    sum: "450,00 ₽",
  },
]

/**
 * Отображение данных: то, во что превращаются расходы после сохранения —
 * статус, метрика, строка таблицы, участник. Оба состояния таблицы сверены
 * буквально с routes/expenses.tsx: пустая — строка с colSpan внутри тела
 * таблицы, а не отдельная карточка. Категории в строках — из настоящего
 * списка приложения, иначе витрина показывает разделы, которых нет.
 */
export function DataShowcase() {
  return (
    <Group
      title="Отображение данных"
      note="Те же карточки, бейджи и таблицы, что показывают уже сохранённые записи, — включая пустые и загружающиеся."
    >
      <Section title="Роли и статусы" note="Права: viewer, editor, admin.">
        <div className="flex flex-wrap items-center gap-2">
          <Badge>admin</Badge>
          <Badge variant="secondary">editor</Badge>
          <Badge variant="outline">viewer</Badge>
          <Badge variant="destructive">отключён</Badge>
        </div>
      </Section>

      <Section title="Карточки-метрики" note="Тот же приём, что на /expenses.">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Card>
            <CardHeader>
              <CardDescription>Всего</CardDescription>
              <CardTitle className="text-lg">34 930,00 ₽</CardTitle>
            </CardHeader>
          </Card>
          <Card>
            <CardHeader>
              <CardDescription>Подписки · 7%</CardDescription>
              <CardTitle className="text-lg">2 490,00 ₽</CardTitle>
            </CardHeader>
          </Card>
          <Card>
            <CardHeader>
              <CardDescription>Техника · 92%</CardDescription>
              <CardTitle className="text-lg">31 990,00 ₽</CardTitle>
            </CardHeader>
          </Card>
          <Card>
            <CardHeader>
              <CardDescription>Логистика · 1%</CardDescription>
              <CardTitle className="text-lg">450,00 ₽</CardTitle>
            </CardHeader>
          </Card>
        </div>
      </Section>

      <Section
        title="Таблица"
        note="Оба состояния раздела — с данными и пустое, — колонки как в /expenses."
      >
        <div className="flex flex-col gap-2">
          <p className="text-sm text-muted-foreground">С данными</p>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Дата</TableHead>
                <TableHead>Назначение</TableHead>
                <TableHead>Категория</TableHead>
                <TableHead className="text-right">Сумма</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {ROWS.map((r) => (
                <TableRow key={r.title}>
                  <TableCell>{r.date}</TableCell>
                  <TableCell>{r.title}</TableCell>
                  <TableCell>{r.category}</TableCell>
                  <TableCell className="text-right">{r.sum}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>

        <div className="flex flex-col gap-2">
          <p className="text-sm text-muted-foreground">Пустая</p>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Дата</TableHead>
                <TableHead>Назначение</TableHead>
                <TableHead>Категория</TableHead>
                <TableHead className="text-right">Сумма</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              <TableRow>
                <TableCell colSpan={4} className="text-muted-foreground">
                  Пока ничего не добавлено — заполни форму выше.
                </TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </div>
      </Section>

      <Section
        title="Аватар"
        note="Инициалы — запасной вариант без фото; бейдж статуса и групповая шапка для нескольких участников."
      >
        <div className="flex flex-wrap items-end gap-6">
          <Avatar size="sm">
            <AvatarFallback>КМ</AvatarFallback>
          </Avatar>
          <Avatar>
            <AvatarFallback>НВ</AvatarFallback>
          </Avatar>
          <Avatar size="lg">
            <AvatarFallback>АБ</AvatarFallback>
            <AvatarBadge className="bg-success text-success-foreground" />
          </Avatar>
          <AvatarGroup>
            <Avatar>
              <AvatarFallback>ЕЖ</AvatarFallback>
            </Avatar>
            <Avatar>
              <AvatarFallback>ЗИ</AvatarFallback>
            </Avatar>
            <Avatar>
              <AvatarFallback>КЛ</AvatarFallback>
            </Avatar>
          </AvatarGroup>
        </div>
      </Section>

      <Section
        title="Прогресс"
        note="Определённое значение и неопределённая загрузка — без оценки времени полоса стоит пустой, это не поломка."
      >
        <div className="flex max-w-sm flex-col gap-4">
          {/*
            locale="ru-RU" задан явно и не по вкусу: без него ProgressValue
            берёт локаль браузера, а Intl.NumberFormat форматирует процент
            по-разному от локали к локали ("62 %" против "62%"). Число на
            витрине не должно зависеть от настроек того, кто её открыл, —
            по той же причине даты и суммы приложение форматирует своим
            lib/format.ts, а не как получится.
          */}
          <Progress value={62} locale="ru-RU">
            {/* w-full обязателен: корень Progress — это flex-строка, и
                без него подпись со значением сжимаются по содержимому,
                justify-between раздвигать нечего, и на экране выходит
                слипшееся «Загружено чеков62 %». */}
            <div className="flex w-full justify-between">
              <ProgressLabel>Загружено чеков</ProgressLabel>
              <ProgressValue />
            </div>
          </Progress>
          <Progress value={null} locale="ru-RU">
            <ProgressLabel>Синхронизация с банком</ProgressLabel>
          </Progress>
        </div>
      </Section>

      <Section
        title="Скелет загрузки"
        note="Заглушка на время запроса — тот же ритм, что у карточек-метрик выше."
      >
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {[0, 1, 2, 3].map((i) => (
            <Card key={i}>
              <CardHeader className="gap-2">
                <Skeleton className="h-3 w-20" />
                <Skeleton className="h-5 w-28" />
              </CardHeader>
            </Card>
          ))}
        </div>
      </Section>

      <Section
        title="Разделитель"
        note="Горизонтальный — между блоками, вертикальный — внутри строки."
      >
        <div className="flex flex-col gap-4">
          <Separator />
          <div className="flex h-5 items-center gap-4 text-sm text-muted-foreground">
            <span>Расходы</span>
            <Separator orientation="vertical" />
            <span>Пользователи</span>
            <Separator orientation="vertical" />
            <span>Журнал</span>
          </div>
        </div>
      </Section>
    </Group>
  )
}
