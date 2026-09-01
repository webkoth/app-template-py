import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Checkbox } from "@/components/ui/checkbox"
import { Switch } from "@/components/ui/switch"
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group"
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { CATEGORIES } from "@/routes/expenses"
import { Group, Section } from "./showcase-section"

/**
 * Ввод и формы: то же самое, из чего собрана форма /expenses. Ошибка здесь
 * не украшение — форма расходов показывает её ровно так, текстом рядом с
 * полем в text-destructive, без aria-invalid, которого настоящие формы
 * проекта не ставят никогда.
 *
 * Категории берутся из /expenses, а не переписаны сюда списком: витрина,
 * разошедшаяся с приложением, показывает владельцу оформление, которого у
 * него не будет, а агенту — образец не того экрана.
 *
 * В эталоне (Next) Select жил отдельным файлом: он клиентский, а витрина
 * была серверным компонентом. Здесь SPA, клиентское всё, и делить не на
 * что — поле стоит прямо в своей секции.
 */
export function FormsShowcase() {
  return (
    <Group
      title="Ввод и формы"
      note="Элементы, которыми человек передаёт данные, — от кнопки до текста ошибки, возвращённого формой."
    >
      <Section title="Кнопки" note="Главное действие, второстепенное, опасное.">
        <div className="flex flex-wrap items-center gap-2">
          <Button>Добавить</Button>
          <Button variant="secondary">Вторичная</Button>
          <Button variant="outline">С рамкой</Button>
          <Button variant="ghost">Призрак</Button>
          <Button variant="destructive">Удалить</Button>
          <Button variant="link">Ссылка</Button>
          <Button disabled>Недоступна</Button>
        </div>
      </Section>

      <Section
        title="Поля и ошибки"
        note="Ошибка возвращается формой, а не бросается: так устроены все мутации."
      >
        <div className="flex flex-col gap-4 sm:flex-row sm:items-end">
          <div className="flex flex-col gap-2">
            <Label htmlFor="showcase-title">Назначение</Label>
            <Input id="showcase-title" defaultValue="Подписка на трекер" />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="showcase-category">Категория</Label>
            <Select defaultValue={CATEGORIES[0]}>
              <SelectTrigger id="showcase-category" className="w-48">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
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
          <div className="flex flex-col gap-2">
            <Label htmlFor="showcase-amount">Сумма</Label>
            <Input id="showcase-amount" defaultValue="двенадцать" />
          </div>
          <Button>Сохранить</Button>
          <p role="alert" className="text-sm text-destructive">
            Сумма не похожа на число
          </p>
        </div>
      </Section>

      <Section
        title="Многострочное поле"
        note="Растёт по содержимому — field-sizing-content, а не фиксированная высота."
      >
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start">
          <div className="flex flex-1 flex-col gap-2">
            <Label htmlFor="showcase-comment">Комментарий</Label>
            <Textarea
              id="showcase-comment"
              defaultValue="Оплатили картой компании, чек пришёл на почту бухгалтерии."
            />
          </div>
          <div className="flex flex-1 flex-col gap-2">
            <Label htmlFor="showcase-comment-disabled">
              Комментарий (недоступно)
            </Label>
            <Textarea
              id="showcase-comment-disabled"
              disabled
              defaultValue="Поле закрыто для правки после согласования"
            />
          </div>
        </div>
      </Section>

      <Section
        title="Чекбокс"
        note="Согласие и множественный выбор — можно отметить сразу несколько."
      >
        <div className="flex flex-col gap-3">
          <div className="flex items-center gap-2">
            <Checkbox id="showcase-check-1" defaultChecked />
            <Label htmlFor="showcase-check-1">
              Уведомлять о новых расходах
            </Label>
          </div>
          <div className="flex items-center gap-2">
            <Checkbox id="showcase-check-2" />
            <Label htmlFor="showcase-check-2">
              Включить в еженедельный отчёт
            </Label>
          </div>
          <div className="flex items-center gap-2">
            <Checkbox id="showcase-check-3" disabled />
            <Label htmlFor="showcase-check-3" className="text-muted-foreground">
              Автосписание — недоступно на этом тарифе
            </Label>
          </div>
        </div>
      </Section>

      <Section
        title="Переключатель"
        note="Бинарная настройка, которая применяется сразу — без кнопки «Сохранить»."
      >
        <div className="flex flex-col gap-3">
          <div className="flex items-center gap-2">
            <Switch id="showcase-switch-1" defaultChecked />
            <Label htmlFor="showcase-switch-1">Тёмная тема по умолчанию</Label>
          </div>
          <div className="flex items-center gap-2">
            <Switch id="showcase-switch-2" disabled />
            <Label
              htmlFor="showcase-switch-2"
              className="text-muted-foreground"
            >
              Двухфакторная защита — скоро
            </Label>
          </div>
        </div>
      </Section>

      <Section
        title="Радиогруппа"
        note="Один вариант из нескольких — не список статусов и не независимые чекбоксы."
      >
        <RadioGroup defaultValue="month" className="max-w-xs">
          <div className="flex items-center gap-2">
            <RadioGroupItem value="week" id="showcase-radio-week" />
            <Label htmlFor="showcase-radio-week">Неделя</Label>
          </div>
          <div className="flex items-center gap-2">
            <RadioGroupItem value="month" id="showcase-radio-month" />
            <Label htmlFor="showcase-radio-month">Месяц</Label>
          </div>
          <div className="flex items-center gap-2">
            <RadioGroupItem value="year" id="showcase-radio-year" disabled />
            <Label
              htmlFor="showcase-radio-year"
              className="text-muted-foreground"
            >
              Год — нет данных за такой период
            </Label>
          </div>
        </RadioGroup>
      </Section>
    </Group>
  )
}
