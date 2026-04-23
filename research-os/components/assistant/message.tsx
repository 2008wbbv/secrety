import { CitationPill } from '@/components/assistant/citation-pill'
import type { AssistantMessage as Msg } from '@/types'

interface MessageProps {
  message: Msg
}

function renderWithCitations(content: string, citations: Msg['citations']) {
  if (!citations.length) return <p className="text-sm leading-relaxed whitespace-pre-wrap">{content}</p>

  const parts = content.split(/(\[\d+\])/g)
  return (
    <p className="text-sm leading-relaxed">
      {parts.map((part, i) => {
        const match = part.match(/^\[(\d+)\]$/)
        if (match) {
          const idx = parseInt(match[1])
          const citation = citations.find((c) => c.index === idx)
          return citation ? <CitationPill key={i} citation={citation} /> : <span key={i}>{part}</span>
        }
        return <span key={i}>{part}</span>
      })}
    </p>
  )
}

export function AssistantMessage({ message }: MessageProps) {
  const isUser = message.role === 'user'

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[80%] rounded-lg px-4 py-2.5 ${
          isUser ? 'bg-primary text-primary-foreground' : 'bg-muted'
        }`}
      >
        {isUser ? (
          <p className="text-sm leading-relaxed">{message.content}</p>
        ) : (
          renderWithCitations(message.content, message.citations)
        )}
        {message.citations.length > 0 && (
          <div className="flex flex-wrap gap-1 mt-2 border-t border-border/30 pt-2">
            {message.citations.map((c) => (
              <CitationPill key={c.chunk_id} citation={c} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
