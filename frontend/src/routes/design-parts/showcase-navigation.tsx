import { Button } from "@/components/ui/button"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { FolderInputIcon, PencilIcon, Trash2Icon } from "lucide-react"
import { CATEGORIES } from "@/routes/expenses"
import { Group, Section } from "./showcase-section"

/**
 * Навигация: переключение внутри страницы (вкладки) и меню действий над
 * записью. Пункты меню — всегда внутри DropdownMenuGroup (AGENTS.md,
 * «Интерфейс»): без обёртки при раскрытом поддменю края прижимаются.
 * Поддменю здесь показывает этот приём живьём, а не только на словах, и
 * группа стоит и в корневом меню, и внутри поддменю.
 *
 * Категории — те же, что в /expenses, импортом, а не копией списка.
 */
export function NavigationShowcase() {
  return (
    <Group
      title="Навигация"
      note="Переключение экрана без ухода со страницы и меню действий над записью."
    >
      <Section
        title="Вкладки"
        note="Активный список, архив и пустое состояние — черновиков может не быть."
      >
        <Tabs defaultValue="active" className="max-w-md">
          <TabsList>
            <TabsTrigger value="active">Активные</TabsTrigger>
            <TabsTrigger value="archived">Архив</TabsTrigger>
            <TabsTrigger value="drafts">Черновики</TabsTrigger>
          </TabsList>
          <TabsContent value="active" className="flex flex-col gap-2 pt-3">
            <p className="text-sm">Подписка на трекер — 2 490,00 ₽</p>
            <p className="text-sm">Монитор — 31 990,00 ₽</p>
          </TabsContent>
          <TabsContent value="archived" className="flex flex-col gap-2 pt-3">
            <p className="text-sm text-muted-foreground">
              Курьерская доставка — 450,00 ₽ (в архиве с 01.08.2026)
            </p>
          </TabsContent>
          <TabsContent value="drafts" className="pt-3">
            <p className="text-sm text-muted-foreground">
              Черновиков пока нет — они появляются здесь, если форму закрыли, не
              сохранив.
            </p>
          </TabsContent>
        </Tabs>
      </Section>

      <Section
        title="Выпадающее меню"
        note="Пункты — в группе, поддменю переносит запись в другую категорию."
      >
        {/*
          Section оборачивает содержимое в flex-col, а он растягивает прямых
          детей на всю ширину (align-items: stretch по умолчанию) — без
          этого div кнопка триггера расползается на всю строку. Тот же
          приём — выше, у диалога.
        */}
        <div className="flex flex-wrap items-center gap-2">
          <DropdownMenu>
            <DropdownMenuTrigger render={<Button variant="outline" />}>
              Действия
            </DropdownMenuTrigger>
            {/*
              min-w-56: без явной ширины поповер наследует w-(--anchor-width)
              — ширину триггера («Действия», это узкая кнопка), и пункту с
              иконкой и шевроном поддменю уже не хватает места на одну
              строку.
            */}
            <DropdownMenuContent className="min-w-56">
              <DropdownMenuGroup>
                <DropdownMenuItem>
                  <PencilIcon />
                  Изменить
                </DropdownMenuItem>
                <DropdownMenuSub>
                  <DropdownMenuSubTrigger>
                    <FolderInputIcon />В категорию
                  </DropdownMenuSubTrigger>
                  <DropdownMenuSubContent>
                    <DropdownMenuGroup>
                      {CATEGORIES.map((c) => (
                        <DropdownMenuItem key={c}>{c}</DropdownMenuItem>
                      ))}
                    </DropdownMenuGroup>
                  </DropdownMenuSubContent>
                </DropdownMenuSub>
                <DropdownMenuSeparator />
                <DropdownMenuItem variant="destructive">
                  <Trash2Icon />
                  Удалить
                </DropdownMenuItem>
              </DropdownMenuGroup>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </Section>
    </Group>
  )
}
