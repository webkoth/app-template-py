import { PageMain } from "@/components/page-main"
import { ChartsShowcase } from "./design-parts/showcase-charts"
import { DataShowcase } from "./design-parts/showcase-data"
import { FeedbackShowcase } from "./design-parts/showcase-feedback"
import { FormsShowcase } from "./design-parts/showcase-forms"
import { NavigationShowcase } from "./design-parts/showcase-navigation"
import { Group } from "./design-parts/showcase-section"
import { ThemePicker } from "./design-parts/theme-picker"

/**
 * Витрина всех установленных компонентов в рабочих состояниях. Удаляется
 * целиком, когда шаблон стал приложением и оформление выбрано; lib/design
 * при этом остаётся — команда npm run theme работает и без витрины.
 *
 * Живёт отдельно от «/» намеренно. Стартовая отвечает на вопросы «что это»
 * и «как начать» — витрина на ней вытесняла ответы вниз, а нужна она не
 * каждый день, а когда строят экран или выбирают оформление.
 */
export function DesignPage() {
  return (
    <PageMain>
      <h1 className="text-3xl font-semibold">Дизайн</h1>
      <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
        Те же компоненты, из которых собраны разделы приложения, в рабочих
        состояниях — включая пустые списки, ошибки и загрузку. Новые экраны
        выглядят так же: это не отдельная витринная вёрстка.
      </p>
      <div className="mt-10 flex flex-col gap-16">
        {/* Примерка тем — такая же секция витрины, как остальные, и
            заголовок ей нужен по той же причине: без него пять цветных
            карточек висят над «Ввод и формы» без объяснения, что это
            вообще и почему после обновления страницы пропадёт. */}
        <Group
          title="Оформление"
          note="Пять готовых тем. Примерка идёт живьём и ничего не сохраняет: обнови страницу — вернётся тема проекта. Выбранная тема вписывается в стили командой npm run theme и уезжает на контур одна."
        >
          <ThemePicker />
        </Group>
        <FormsShowcase />
        <DataShowcase />
        <FeedbackShowcase />
        <NavigationShowcase />
        <ChartsShowcase />
      </div>
    </PageMain>
  )
}
