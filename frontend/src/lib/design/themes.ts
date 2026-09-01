/**
 * Темы оформления. Единственное место в проекте, где записаны значения
 * цветов: правило линтера запрещает литеральные цвета в app/** и
 * components/**, а lib/** под него не попадает — значению цвета место
 * рядом с определением темы.
 *
 * Тема объявляет девять значений на режим. Полный набор из сорока токенов
 * разворачивает buildThemeCss из ./css.ts: держать сорок значений на режим
 * руками для пяти тем — это четыреста чисел, которые не остаются
 * согласованными.
 */

/** Основа режима: из неё выводятся все поверхностные и текстовые токены. */
export interface Ramp {
  background: string
  foreground: string
  /** Приподнятая поверхность: карточки, поповеры, боковая панель. */
  card: string
  primary: string
  primaryForeground: string
  muted: string
  mutedForeground: string
  border: string
  ring: string
}

export interface Theme {
  /** Им же зовётся команда: npm run theme -- blue */
  name: string
  /** Им же подписана карточка на витрине. */
  label: string
  radius: string
  light: Ramp
  dark: Ramp
}

/**
 * Цвета, общие для всех тем и не зависящие от оформления: статусы (ошибка,
 * успех, предупреждение, информирование, выделение) плюс rose — пятый цвет
 * категориальной палитры графиков. «Ошибка» означает одно и то же в любом
 * оформлении, и разводить статусы по темам значит завести пять способов
 * показать одну и ту же ошибку.
 *
 * info — нейтральное информирование: сообщить нужно, но это не успех и не
 * проблема; для главного действия есть primary.
 * highlight — вторичный акцент для меток и выделения сущностей, не статус.
 * rose — пятый цвет категориальной палитры графиков.
 */
export interface SharedColors {
  destructive: string
  success: string
  successForeground: string
  warning: string
  warningForeground: string
  info: string
  infoForeground: string
  highlight: string
  highlightForeground: string
  /** Пятый цвет категориальной палитры графиков. */
  rose: string
}

export const SHARED_COLORS: Record<"light" | "dark", SharedColors> = {
  light: {
    destructive: "oklch(0.577 0.245 27.325)",
    success: "oklch(0.58 0.14 152)",
    successForeground: "oklch(0.98 0.02 152)",
    warning: "oklch(0.62 0.13 70)",
    warningForeground: "oklch(0.99 0.02 90)",
    info: "oklch(0.53 0.19 262)",
    infoForeground: "oklch(0.98 0.02 262)",
    highlight: "oklch(0.56 0.1 197)",
    highlightForeground: "oklch(0.985 0.02 197)",
    rose: "oklch(0.62 0.2 15)",
  },
  dark: {
    destructive: "oklch(0.704 0.191 22.216)",
    success: "oklch(0.72 0.16 155)",
    successForeground: "oklch(0.16 0.03 155)",
    warning: "oklch(0.8 0.15 80)",
    warningForeground: "oklch(0.18 0.03 80)",
    info: "oklch(0.73 0.14 262)",
    infoForeground: "oklch(0.17 0.04 262)",
    highlight: "oklch(0.76 0.11 197)",
    highlightForeground: "oklch(0.16 0.03 197)",
    rose: "oklch(0.72 0.17 15)",
  },
}

export const THEMES: Theme[] = [
  {
    name: "blue",
    label: "Синяя",
    radius: "0.5rem",
    light: {
      background: "oklch(1 0 0)",
      foreground: "oklch(0.21 0.03 264)",
      card: "oklch(1 0 0)",
      primary: "oklch(0.55 0.22 263)",
      primaryForeground: "oklch(0.98 0.01 264)",
      muted: "oklch(0.968 0.007 264)",
      mutedForeground: "oklch(0.55 0.02 264)",
      border: "oklch(0.928 0.01 264)",
      ring: "oklch(0.55 0.22 263)",
    },
    dark: {
      background: "oklch(0.16 0.02 264)",
      foreground: "oklch(0.98 0.005 264)",
      card: "oklch(0.21 0.025 264)",
      primary: "oklch(0.62 0.19 263)",
      primaryForeground: "oklch(0.15 0.03 264)",
      muted: "oklch(0.27 0.02 264)",
      mutedForeground: "oklch(0.71 0.02 264)",
      border: "oklch(1 0 0 / 12%)",
      ring: "oklch(0.62 0.19 263)",
    },
  },
  {
    name: "neutral",
    label: "Нейтральная",
    radius: "0.625rem",
    light: {
      background: "oklch(1 0 0)",
      foreground: "oklch(0.145 0 0)",
      card: "oklch(1 0 0)",
      primary: "oklch(0.205 0 0)",
      primaryForeground: "oklch(0.985 0 0)",
      muted: "oklch(0.97 0 0)",
      mutedForeground: "oklch(0.556 0 0)",
      border: "oklch(0.922 0 0)",
      ring: "oklch(0.708 0 0)",
    },
    dark: {
      background: "oklch(0.145 0 0)",
      foreground: "oklch(0.985 0 0)",
      card: "oklch(0.205 0 0)",
      primary: "oklch(0.922 0 0)",
      primaryForeground: "oklch(0.205 0 0)",
      muted: "oklch(0.269 0 0)",
      mutedForeground: "oklch(0.708 0 0)",
      border: "oklch(1 0 0 / 10%)",
      ring: "oklch(0.556 0 0)",
    },
  },
  {
    name: "emerald",
    label: "Изумрудная",
    radius: "0.75rem",
    light: {
      background: "oklch(1 0 0)",
      foreground: "oklch(0.19 0.02 165)",
      card: "oklch(1 0 0)",
      primary: "oklch(0.55 0.13 162)",
      primaryForeground: "oklch(0.98 0.02 162)",
      muted: "oklch(0.965 0.01 165)",
      mutedForeground: "oklch(0.53 0.02 165)",
      border: "oklch(0.92 0.012 165)",
      ring: "oklch(0.55 0.13 162)",
    },
    dark: {
      background: "oklch(0.15 0.02 165)",
      foreground: "oklch(0.97 0.01 165)",
      card: "oklch(0.2 0.025 165)",
      primary: "oklch(0.7 0.14 162)",
      primaryForeground: "oklch(0.15 0.03 162)",
      muted: "oklch(0.26 0.02 165)",
      mutedForeground: "oklch(0.71 0.02 165)",
      border: "oklch(1 0 0 / 12%)",
      ring: "oklch(0.7 0.14 162)",
    },
  },
  {
    name: "graphite",
    label: "Графит с оранжевым",
    radius: "0.375rem",
    light: {
      background: "oklch(0.995 0.002 60)",
      foreground: "oklch(0.17 0.005 60)",
      card: "oklch(1 0 0)",
      primary: "oklch(0.62 0.19 42)",
      primaryForeground: "oklch(0.99 0.01 60)",
      muted: "oklch(0.965 0.006 60)",
      mutedForeground: "oklch(0.53 0.012 60)",
      border: "oklch(0.92 0.008 60)",
      ring: "oklch(0.62 0.19 42)",
    },
    dark: {
      background: "oklch(0.14 0.005 60)",
      foreground: "oklch(0.98 0.004 60)",
      card: "oklch(0.19 0.006 60)",
      primary: "oklch(0.7 0.17 45)",
      primaryForeground: "oklch(0.16 0.02 45)",
      muted: "oklch(0.26 0.008 60)",
      mutedForeground: "oklch(0.71 0.012 60)",
      border: "oklch(1 0 0 / 12%)",
      ring: "oklch(0.7 0.17 45)",
    },
  },
  {
    name: "violet",
    label: "Фиолетовая",
    radius: "0.875rem",
    light: {
      background: "oklch(1 0 0)",
      foreground: "oklch(0.19 0.02 295)",
      card: "oklch(1 0 0)",
      primary: "oklch(0.54 0.24 293)",
      primaryForeground: "oklch(0.98 0.01 293)",
      muted: "oklch(0.968 0.008 295)",
      mutedForeground: "oklch(0.54 0.02 295)",
      border: "oklch(0.925 0.012 295)",
      ring: "oklch(0.54 0.24 293)",
    },
    dark: {
      background: "oklch(0.15 0.02 295)",
      foreground: "oklch(0.98 0.008 295)",
      card: "oklch(0.2 0.025 295)",
      primary: "oklch(0.65 0.2 293)",
      primaryForeground: "oklch(0.15 0.03 293)",
      muted: "oklch(0.27 0.02 295)",
      mutedForeground: "oklch(0.72 0.02 295)",
      border: "oklch(1 0 0 / 12%)",
      ring: "oklch(0.65 0.2 293)",
    },
  },
]

/** Тема шаблона по умолчанию. Решение владельца. */
export const DEFAULT_THEME = "blue"

export function findTheme(name: string): Theme | undefined {
  return THEMES.find((t) => t.name === name)
}
