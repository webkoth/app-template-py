/**
 * Group — заголовок + подпись над смысловым блоком витрины (ввод и формы,
 * отображение данных и т.д.). Section — то же самое уровнем ниже, над одним
 * компонентом внутри блока. Общие для всех файлов группы витрины, чтобы у
 * них был одинаковый вид независимо от того, в каком файле они собраны.
 */
export function Group({
  title,
  note,
  children,
}: {
  title: string
  note: string
  children: React.ReactNode
}) {
  return (
    <section className="flex flex-col gap-6">
      <div>
        <h2 className="text-lg font-medium">{title}</h2>
        <p className="max-w-2xl text-sm text-muted-foreground">{note}</p>
      </div>
      <div className="flex flex-col gap-10">{children}</div>
    </section>
  )
}

export function Section({
  title,
  note,
  children,
}: {
  title: string
  note: string
  children: React.ReactNode
}) {
  return (
    <section className="flex flex-col gap-3">
      <div>
        <h3 className="text-sm font-medium">{title}</h3>
        <p className="text-sm text-muted-foreground">{note}</p>
      </div>
      {children}
    </section>
  )
}
