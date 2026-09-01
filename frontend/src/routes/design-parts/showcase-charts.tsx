import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  XAxis,
  YAxis,
} from "recharts"
import {
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart"
import { Group, Section } from "./showcase-section"

// components/ui/chart.tsx даёт только обвязку (ChartContainer и т.д.), а
// BarChart/Line/Pie и оси собираются в файле, который их использует, — так
// же, как в любом стандартном примере shadcn charts.

const MONTHLY_DATA = [
  { month: "Апр", plan: 32000, actual: 28400 },
  { month: "Май", plan: 34000, actual: 35100 },
  { month: "Июн", plan: 30000, actual: 26800 },
  { month: "Июл", plan: 36000, actual: 38900 },
  { month: "Авг", plan: 35000, actual: 34930 },
]

const MONTHLY_CONFIG = {
  plan: { label: "План", color: "var(--chart-2)" },
  actual: { label: "Факт", color: "var(--chart-1)" },
} satisfies ChartConfig

const CUMULATIVE_DATA = [
  { day: "1", current: 0, previous: 0 },
  { day: "5", current: 4200, previous: 3100 },
  { day: "10", current: 9800, previous: 9700 },
  { day: "15", current: 15400, previous: 18200 },
  { day: "20", current: 24100, previous: 24600 },
  { day: "25", current: 30950, previous: 29800 },
  { day: "28", current: 34930, previous: 33950 },
]

const CUMULATIVE_CONFIG = {
  current: { label: "Этот месяц", color: "var(--chart-1)" },
  previous: { label: "Прошлый месяц", color: "var(--chart-3)" },
} satisfies ChartConfig

// Слаги-ключи, не кириллица: --color-<key> становится именем
// CSS-переменной, а категории приложения (CATEGORIES в routes/expenses.tsx)
// записаны по-русски — те же подписи здесь идут в config.label. Категории
// перечислены все пять: круговая на четырёх выглядела бы иначе, чем на
// настоящих данных, а пятый цвет палитры (--chart-5) не проверялся бы
// глазами вовсе.
const CATEGORY_CONFIG = {
  rent: { label: "Аренда", color: "var(--chart-1)" },
  software: { label: "Софт", color: "var(--chart-2)" },
  hardware: { label: "Оборудование", color: "var(--chart-3)" },
  services: { label: "Услуги", color: "var(--chart-4)" },
  other: { label: "Прочее", color: "var(--chart-5)" },
} satisfies ChartConfig

const CATEGORY_DATA = [
  { key: "rent", amount: 60000, fill: "var(--color-rent)" },
  { key: "software", amount: 2490, fill: "var(--color-software)" },
  { key: "hardware", amount: 31990, fill: "var(--color-hardware)" },
  { key: "services", amount: 1200, fill: "var(--color-services)" },
  { key: "other", amount: 450, fill: "var(--color-other)" },
]

/**
 * Графики: столбцы, линия и круговая — три разных по форме способа
 * показать одни и те же расходы. Цвет только из config.color
 * (--chart-1…5): ChartContainer превращает его в --color-<ключ> и
 * прокидывает в fill/stroke ниже, других цветов в файле нет.
 *
 * С темой меняется --chart-1 — она берётся из primary выбранной темы
 * (lib/design/css.ts). Остальные четыре токена палитры общие для всех тем
 * намеренно: категориальные цвета должны различаться между собой, а не
 * следовать оформлению, иначе на изумрудной теме пять зелёных долей круга
 * перестают отличаться друг от друга. Примерка темы выше на этой же
 * странице показывает это живьём.
 */
export function ChartsShowcase() {
  return (
    <Group
      title="Графики"
      note="Столбцы, линия и круговая — цвета только из токенов --chart-1…5 через ChartConfig. С темой меняется первый из них, остальные общие для всех тем: категориальные цвета обязаны отличаться друг от друга."
    >
      <Section
        title="План и факт по месяцам"
        note="Группированные столбцы — сравнение двух величин одного масштаба."
      >
        <ChartContainer
          config={MONTHLY_CONFIG}
          className="h-64 w-full max-w-2xl"
        >
          <BarChart data={MONTHLY_DATA}>
            <CartesianGrid vertical={false} />
            <XAxis
              dataKey="month"
              tickLine={false}
              axisLine={false}
              tickMargin={8}
            />
            <YAxis tickLine={false} axisLine={false} width={44} />
            <ChartTooltip content={<ChartTooltipContent />} />
            <ChartLegend content={<ChartLegendContent />} />
            <Bar dataKey="plan" fill="var(--color-plan)" radius={4} />
            <Bar dataKey="actual" fill="var(--color-actual)" radius={4} />
          </BarChart>
        </ChartContainer>
      </Section>

      <Section
        title="Расходы нарастающим итогом"
        note="Линия — динамика во времени, этот месяц против прошлого."
      >
        <ChartContainer
          config={CUMULATIVE_CONFIG}
          className="h-64 w-full max-w-2xl"
        >
          <LineChart data={CUMULATIVE_DATA}>
            <CartesianGrid vertical={false} />
            <XAxis
              dataKey="day"
              tickLine={false}
              axisLine={false}
              tickMargin={8}
            />
            <YAxis tickLine={false} axisLine={false} width={44} />
            <ChartTooltip content={<ChartTooltipContent indicator="line" />} />
            <ChartLegend content={<ChartLegendContent />} />
            <Line
              type="monotone"
              dataKey="current"
              stroke="var(--color-current)"
              strokeWidth={2}
              dot={false}
            />
            <Line
              type="monotone"
              dataKey="previous"
              stroke="var(--color-previous)"
              strokeWidth={2}
              strokeDasharray="4 4"
              dot={false}
            />
          </LineChart>
        </ChartContainer>
      </Section>

      <Section
        title="Доля по категориям"
        note="Круговая — распределение одной величины по идентичности, не по времени."
      >
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
          <ChartContainer
            config={CATEGORY_CONFIG}
            className="h-64 w-full max-w-xs"
          >
            <PieChart>
              <ChartTooltip
                content={<ChartTooltipContent nameKey="key" hideLabel />}
              />
              <Pie
                data={CATEGORY_DATA}
                dataKey="amount"
                nameKey="key"
                innerRadius={50}
              >
                {CATEGORY_DATA.map((item) => (
                  <Cell key={item.key} fill={item.fill} />
                ))}
              </Pie>
              <ChartLegend content={<ChartLegendContent nameKey="key" />} />
            </PieChart>
          </ChartContainer>
          <p className="text-sm text-muted-foreground sm:max-w-40">
            Без расходов за период круг не рисуется — здесь тот же текст, что и
            у пустой таблицы выше: «Пока ничего не добавлено».
          </p>
        </div>
      </Section>
    </Group>
  )
}
