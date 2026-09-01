import { Button } from "@/components/ui/button"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { InfoIcon, RefreshCwIcon, TriangleAlertIcon } from "lucide-react"
import { Group, Section } from "./showcase-section"

/**
 * Обратная связь: то, что сообщает человеку о результате или просит
 * подтверждение — не поверх формы (уведомление рядом с полями), не без
 * возможности передумать (диалог с «Отмена» отдельно от опасной кнопки).
 */
export function FeedbackShowcase() {
  return (
    <Group
      title="Обратная связь"
      note="Уведомление, подтверждение опасного действия и короткая подсказка — три разных по весу способа что-то сообщить."
    >
      <Section
        title="Уведомление"
        note="Информирует и предупреждает об ошибке — рядом с содержимым, не поверх него."
      >
        <div className="flex flex-col gap-3">
          <Alert>
            <InfoIcon />
            <AlertTitle>Резервная копия сегодня уже снята</AlertTitle>
            <AlertDescription>
              Следующая — завтра в 03:00 по московскому времени.
            </AlertDescription>
          </Alert>
          <Alert variant="destructive">
            <TriangleAlertIcon />
            <AlertTitle>Синхронизация с банком не удалась</AlertTitle>
            <AlertDescription>
              Проверьте токен интеграции на странице настроек и повторите
              попытку.
            </AlertDescription>
          </Alert>
        </div>
      </Section>

      <Section
        title="Диалог"
        note="Подтверждение удаления — то же место, где его просит /expenses."
      >
        {/*
          Section оборачивает содержимое в flex-col, а он растягивает прямых
          детей на всю ширину (align-items: stretch по умолчанию) — без
          этого div кнопка триггера расползается на всю строку. Тот же
          приём — ниже, у выпадающего меню.
        */}
        <div className="flex flex-wrap items-center gap-2">
          <Dialog>
            <DialogTrigger render={<Button variant="destructive" />}>
              Удалить расход
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Удалить расход навсегда?</DialogTitle>
                <DialogDescription>
                  Запись «Подписка на трекер» на 2 490,00 ₽ исчезнет из отчётов.
                  Действие нельзя отменить.
                </DialogDescription>
              </DialogHeader>
              <DialogFooter>
                <DialogClose render={<Button variant="outline" />}>
                  Отмена
                </DialogClose>
                <Button variant="destructive">Удалить</Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>
      </Section>

      <Section
        title="Подсказка"
        note="Короткая подсказка при наведении — не замена подписи поля."
      >
        <Tooltip>
          <TooltipTrigger render={<Button variant="outline" size="icon" />}>
            <RefreshCwIcon />
            <span className="sr-only">Обновить данные из банка</span>
          </TooltipTrigger>
          <TooltipContent>Обновить данные из банка</TooltipContent>
        </Tooltip>
      </Section>
    </Group>
  )
}
