'use client'

import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'next/navigation'
import { Send, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { ScrollArea } from '@/components/ui/scroll-area'
import { AssistantMessage } from '@/components/assistant/message'
import { createClient } from '@/lib/supabase/client'
import type { AssistantMessage as Msg, AssistantThread, Citation } from '@/types'

interface Props {
  userId: string
}

export function ChatPane({ userId }: Props) {
  const searchParams = useSearchParams()
  const threadId = searchParams.get('thread')
  const [messages, setMessages] = useState<Msg[]>([])
  const [thread, setThread] = useState<AssistantThread | null>(null)
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [streamingText, setStreamingText] = useState('')
  const bottomRef = useRef<HTMLDivElement>(null)
  const supabase = createClient()

  useEffect(() => {
    if (!threadId) { setMessages([]); setThread(null); return }

    supabase.from('assistant_threads').select('*').eq('id', threadId).single()
      .then(({ data }) => setThread(data as AssistantThread))

    supabase.from('assistant_messages').select('*').eq('thread_id', threadId).order('created_at')
      .then(({ data }) => setMessages((data ?? []) as Msg[]))
  }, [threadId, supabase])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, streamingText])

  const send = async () => {
    const text = input.trim()
    if (!text || streaming) return
    setInput('')
    setStreaming(true)
    setStreamingText('')

    const userMsg: Msg = {
      id: crypto.randomUUID(),
      thread_id: threadId ?? '',
      role: 'user',
      content: text,
      citations: [],
      created_at: new Date().toISOString(),
    }
    setMessages((prev) => [...prev, userMsg])

    const res = await fetch('/api/assistant', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text, threadId, userId }),
    })

    if (!res.ok || !res.body) {
      setStreaming(false)
      return
    }

    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let fullText = ''
    let citations: Citation[] = []
    let newThreadId = threadId

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      const chunk = decoder.decode(value)
      for (const line of chunk.split('\n')) {
        if (!line.startsWith('data: ')) continue
        const raw = line.slice(6)
        if (raw === '[DONE]') continue
        try {
          const data = JSON.parse(raw) as { type: string; text?: string; citations?: Citation[]; threadId?: string }
          if (data.type === 'text' && data.text) {
            fullText += data.text
            setStreamingText(fullText)
          }
          if (data.type === 'citations') citations = data.citations ?? []
          if (data.type === 'threadId') newThreadId = data.threadId ?? null
        } catch { /* ignore parse errors */ }
      }
    }

    const assistantMsg: Msg = {
      id: crypto.randomUUID(),
      thread_id: newThreadId ?? '',
      role: 'assistant',
      content: fullText,
      citations,
      created_at: new Date().toISOString(),
    }
    setMessages((prev) => [...prev, assistantMsg])
    setStreamingText('')
    setStreaming(false)

    if (newThreadId && newThreadId !== threadId) {
      const url = new URL(window.location.href)
      url.searchParams.set('thread', newThreadId)
      window.history.replaceState({}, '', url.toString())
    }
  }

  return (
    <div className="flex flex-col flex-1 overflow-hidden">
      <ScrollArea className="flex-1 px-4 py-4">
        <div className="space-y-4 max-w-2xl mx-auto">
          {messages.length === 0 && !streaming && (
            <div className="text-center text-muted-foreground text-sm py-12">
              Ask anything about your research library. Answers are grounded in your papers.
            </div>
          )}
          {messages.map((m) => <AssistantMessage key={m.id} message={m} />)}
          {streaming && streamingText && (
            <div className="flex justify-start">
              <div className="max-w-[80%] rounded-lg px-4 py-2.5 bg-muted">
                <p className="text-sm leading-relaxed whitespace-pre-wrap">{streamingText}</p>
              </div>
            </div>
          )}
          {streaming && !streamingText && (
            <div className="flex justify-start">
              <div className="rounded-lg px-4 py-2.5 bg-muted">
                <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>
      </ScrollArea>

      <div className="border-t p-4">
        <div className="flex gap-2 max-w-2xl mx-auto">
          <Textarea
            placeholder="Ask a question about your papers..."
            className="min-h-[2.5rem] max-h-32 resize-none"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={streaming}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() }
            }}
          />
          <Button onClick={send} disabled={streaming || !input.trim()} size="icon">
            {streaming ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
          </Button>
        </div>
      </div>
    </div>
  )
}
