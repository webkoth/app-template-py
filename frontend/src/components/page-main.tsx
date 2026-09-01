import type { ReactNode } from "react"
import { cn } from "@/lib/utils"

/**
 * Ширина основного содержимого страницы задаётся ТОЛЬКО здесь. Свой <main>
 * страницы не заводят: иначе ширина расходится от экрана к экрану, и
 * приводить её обратно приходится по одному файлу.
 */
export function PageMain({
  children,
  className,
}: {
  children: ReactNode
  className?: string
}) {
  return (
    <main className={cn("mx-auto w-full max-w-5xl px-4 py-8", className)}>
      {children}
    </main>
  )
}
