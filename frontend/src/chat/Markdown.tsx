import { Fragment, type ReactNode } from 'react'

/**
 * The smallest useful subset of Markdown for assistant replies: **bold**, `code`
 * and paragraphs. The prompt asks the model for nothing fancier, and anything
 * else renders as plain text rather than as stray asterisks.
 */
export function Markdown({ text }: { text: string }) {
  const paragraphs = text.trim().split(/\n{2,}/)
  return (
    <>
      {paragraphs.map((para, i) => (
        <p className="msg__text" key={i}>
          {renderInline(para)}
        </p>
      ))}
    </>
  )
}

const TOKEN = /(\*\*[^*]+\*\*|`[^`]+`)/g

function renderInline(text: string): ReactNode[] {
  return text.split(TOKEN).map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**')) return <strong key={i}>{part.slice(2, -2)}</strong>
    if (part.startsWith('`') && part.endsWith('`')) return <code key={i}>{part.slice(1, -1)}</code>
    return <Fragment key={i}>{part}</Fragment>
  })
}
