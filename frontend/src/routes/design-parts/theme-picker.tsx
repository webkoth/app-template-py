import { useState } from "react"
import { Button } from "@/components/ui/button"
import { buildThemeCss } from "@/lib/design/css"
import { DEFAULT_THEME, THEMES, findTheme } from "@/lib/design/themes"

/**
 * Примерка темы: <style> с переменными выбранной темы подмешивается прямо
 * в страницу и ничего не сохраняет — обновление возвращает тему проекта.
 *
 * В эталоне (Next) здесь стоял охранник useMounted на useSyncExternalStore:
 * инъекция <style> на сервере давала расхождение гидрации, потому что
 * выбранной темы на сервере ещё нет. Здесь SPA — сервер разметку не
 * рисует, гидрации нет, расходиться нечему, и охранник выброшен, а не
 * перенесён: неработающая защита от несуществующей беды переживает
 * переезд, только если её никто не читает.
 */
export function ThemePicker() {
  const [preview, setPreview] = useState<string | null>(null)
  const theme = preview ? findTheme(preview) : undefined

  return (
    <div className="flex flex-col gap-4">
      {/*
        Блок стоит в документе позже index.css, специфичность та же —
        значит побеждает он. !important не нужен. Внутри и :root, и .dark,
        причём .dark идёт вторым, поэтому в тёмной теме выигрывает он.
      */}
      {theme ? <style>{buildThemeCss(theme)}</style> : null}

      <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-5">
        {THEMES.map((t) => (
          <button
            key={t.name}
            type="button"
            onClick={() => setPreview(t.name)}
            data-testid={`theme-${t.name}`}
            aria-pressed={preview === t.name}
            className="flex flex-col gap-2 rounded-lg border border-border p-3 text-left transition-colors hover:bg-muted aria-pressed:border-ring"
          >
            <span className="flex gap-1.5">
              <span
                className="size-5 rounded-full border border-border"
                style={{ background: t.light.primary }}
              />
              <span
                className="size-5 rounded-full border border-border"
                style={{ background: t.light.muted }}
              />
              <span
                className="size-5 rounded-full border border-border"
                style={{ background: t.dark.background }}
              />
            </span>
            <span className="text-sm font-medium">{t.label}</span>
            <code className="text-xs text-muted-foreground">{t.name}</code>
          </button>
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <p className="text-sm text-muted-foreground">
          {theme ? (
            <>
              Примерка. Чтобы оставить насовсем, выполни{" "}
              <code className="font-mono">npm run theme -- {theme.name}</code>
            </>
          ) : (
            <>
              Тема проекта — <code className="font-mono">{DEFAULT_THEME}</code>.
              Нажми на карточку, чтобы примерить другую.
            </>
          )}
        </p>
        {theme ? (
          <Button variant="outline" size="sm" onClick={() => setPreview(null)}>
            Вернуть тему проекта
          </Button>
        ) : null}
      </div>
    </div>
  )
}
