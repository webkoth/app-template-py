import Markdown from "react-markdown"
import remarkGfm from "remark-gfm"
import { cn } from "@/lib/utils"

/**
 * Свойства тега без служебного node.
 *
 * node — узел разобранного дерева; react-markdown кладёт его в props
 * КАЖДОГО заменённого тега. При `{...props}` он уезжает на настоящий тег
 * DOM, и React пишет в консоль предупреждение о нераспознанном свойстве на
 * каждый заголовок, абзац и ячейку таблицы. Консоль, полная предупреждений,
 * перестаёт быть местом, где видно настоящую ошибку.
 *
 * Снимается здесь, а не в каждой из замен ниже: одиннадцать одинаковых
 * разборов props — это одиннадцать мест, где однажды забудут.
 */
function withoutNode<P extends object>(props: P): Omit<P, "node"> {
  const { node: _node, ...rest } = props as P & { node?: unknown }
  return rest
}

/**
 * Показ markdown из репозитория. Содержимое приходит с бэкенда и написано
 * нами же, но react-markdown по умолчанию не пропускает сырой HTML — и
 * плагин, который это включает, здесь не ставится намеренно.
 *
 * Теги подменяются поимённо, а не классом на обёртке: плагина типографики
 * в проекте нет, и без подмены документ показывался бы браузерным
 * умолчанием — Times New Roman посреди приложения на Inter.
 *
 * Порядок в каждой замене один и тот же: сначала {...props}, потом
 * className через cn. Наоборот — а именно так это и было написано
 * сначала — свой класс проигрывает пришедшему из разметки: у блока
 * ```bash react-markdown ставит на <code> класс language-bash, он
 * затирал оформление целиком, и код в блоке выходил простым текстом.
 */
export function MarkdownView({ content }: { content: string }) {
  return (
    <div className="space-y-4 text-sm leading-relaxed">
      <Markdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: (props) => (
            <h1
              {...withoutNode(props)}
              className={cn("mt-8 text-2xl font-semibold", props.className)}
            />
          ),
          h2: (props) => (
            <h2
              {...withoutNode(props)}
              className={cn("mt-8 text-xl font-semibold", props.className)}
            />
          ),
          h3: (props) => (
            <h3
              {...withoutNode(props)}
              className={cn("mt-6 text-lg font-medium", props.className)}
            />
          ),
          p: (props) => (
            <p
              {...withoutNode(props)}
              className={cn("text-muted-foreground", props.className)}
            />
          ),
          a: (props) => (
            <a
              {...withoutNode(props)}
              className={cn(
                "text-foreground underline underline-offset-2",
                props.className
              )}
            />
          ),
          ul: (props) => (
            <ul
              {...withoutNode(props)}
              className={cn("list-disc space-y-1 pl-6", props.className)}
            />
          ),
          ol: (props) => (
            <ol
              {...withoutNode(props)}
              className={cn("list-decimal space-y-1 pl-6", props.className)}
            />
          ),
          blockquote: (props) => (
            <blockquote
              {...withoutNode(props)}
              className={cn("border-l-2 border-border pl-4", props.className)}
            />
          ),
          // Блок кода: рамка и прокрутка — на <pre>, а вложенному <code>
          // фон и отступы снимаются. Иначе плашка встроенного кода
          // повторяется внутри плашки блока — рамка в рамке.
          pre: (props) => (
            <pre
              {...withoutNode(props)}
              className={cn(
                "overflow-x-auto rounded-md bg-muted p-3 text-xs [&_code]:bg-transparent [&_code]:p-0",
                props.className
              )}
            />
          ),
          code: (props) => (
            <code
              {...withoutNode(props)}
              className={cn(
                "rounded bg-muted px-1.5 py-0.5 text-xs",
                props.className
              )}
            />
          ),
          table: (props) => (
            <div className="overflow-x-auto">
              <table
                {...withoutNode(props)}
                className={cn("w-full text-left", props.className)}
              />
            </div>
          ),
          th: (props) => (
            <th
              {...withoutNode(props)}
              className={cn("border-b border-border p-2", props.className)}
            />
          ),
          td: (props) => (
            <td
              {...withoutNode(props)}
              className={cn("border-b border-border p-2", props.className)}
            />
          ),
        }}
      >
        {content}
      </Markdown>
    </div>
  )
}
