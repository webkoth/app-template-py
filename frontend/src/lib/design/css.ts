/**
 * Сборка CSS темы. Чистая функция: её результат и инъектится в страницу для
 * превью, и вписывается в app/globals.css командой npm run theme. Поэтому
 * «как выглядело» и «что применилось» не могут разойтись.
 *
 * Правила вывода взяты из самого globals.css, каким он был до появления тем:
 * поповер повторяет карточку, secondary и accent равны muted, input равен
 * границе. Боковая панель собирается из тех же значений — отдельной палитры
 * у неё нет.
 */

import {
  SHARED_COLORS,
  type Ramp,
  type SharedColors,
  type Theme,
} from "./themes"

const INDENT = "    "

function declarations(ramp: Ramp, shared: SharedColors): [string, string][] {
  return [
    ["--background", ramp.background],
    ["--foreground", ramp.foreground],
    ["--card", ramp.card],
    ["--card-foreground", ramp.foreground],
    ["--popover", ramp.card],
    ["--popover-foreground", ramp.foreground],
    ["--primary", ramp.primary],
    ["--primary-foreground", ramp.primaryForeground],
    ["--secondary", ramp.muted],
    ["--secondary-foreground", ramp.foreground],
    ["--muted", ramp.muted],
    ["--muted-foreground", ramp.mutedForeground],
    ["--accent", ramp.muted],
    ["--accent-foreground", ramp.foreground],
    ["--destructive", shared.destructive],
    ["--success", shared.success],
    ["--success-foreground", shared.successForeground],
    ["--warning", shared.warning],
    ["--warning-foreground", shared.warningForeground],
    ["--info", shared.info],
    ["--info-foreground", shared.infoForeground],
    ["--highlight", shared.highlight],
    ["--highlight-foreground", shared.highlightForeground],
    ["--border", ramp.border],
    ["--input", ramp.border],
    ["--ring", ramp.ring],
    // Категориальная палитра: главный акцент, бирюзовый, синий, жёлтый, роза.
    ["--chart-1", ramp.primary],
    ["--chart-2", shared.highlight],
    ["--chart-3", shared.info],
    ["--chart-4", shared.warning],
    ["--chart-5", shared.rose],
    ["--sidebar", ramp.card],
    ["--sidebar-foreground", ramp.foreground],
    ["--sidebar-primary", ramp.primary],
    ["--sidebar-primary-foreground", ramp.primaryForeground],
    ["--sidebar-accent", ramp.muted],
    ["--sidebar-accent-foreground", ramp.foreground],
    ["--sidebar-border", ramp.border],
    ["--sidebar-ring", ramp.ring],
  ]
}

function rule(selector: string, pairs: [string, string][]): string {
  const body = pairs.map(([k, v]) => `${INDENT}${k}: ${v};`).join("\n")
  return `${selector} {\n${body}\n}`
}

export function buildThemeCss(theme: Theme): string {
  // Радиус только в :root: от режима он не зависит, а объявленный дважды
  // однажды разойдётся между светлой и тёмной.
  const light: [string, string][] = [
    ...declarations(theme.light, SHARED_COLORS.light),
    ["--radius", theme.radius],
  ]
  return [
    rule(":root", light),
    rule(".dark", declarations(theme.dark, SHARED_COLORS.dark)),
  ].join("\n\n")
}
