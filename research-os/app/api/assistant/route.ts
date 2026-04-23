import { NextResponse } from 'next/server'
import { createClient } from '@/lib/supabase/server'
import { createAdminClient } from '@/lib/supabase/admin'
import { anthropic, CLAUDE_MODEL } from '@/lib/llm/claude'
import { ASSISTANT_SYSTEM, buildAssistantContext } from '@/lib/llm/prompts/assistant'
import { searchChunks } from '@/lib/rag/search'
import type { Citation, ChunkWithPaper } from '@/types'

function extractCitations(text: string, chunks: ChunkWithPaper[]): Citation[] {
  const indices = Array.from(new Set(Array.from(text.matchAll(/\[(\d+)\]/g)).map((m) => parseInt(m[1]))))
  return indices
    .filter((i) => i >= 1 && i <= chunks.length)
    .map((i) => {
      const c = chunks[i - 1]
      return {
        index: i,
        chunk_id: c.id,
        paper_id: c.paper_id,
        paper_title: c.paper.title,
        page_number: c.page_number,
      }
    })
}

export async function POST(request: Request): Promise<Response> {
  const supabase = createClient()
  const { data: { user } } = await supabase.auth.getUser()
  if (!user) return NextResponse.json({ error: 'Unauthorized', code: 401 }, { status: 401 })

  const body = await request.json() as { message?: string; threadId?: string | null; userId?: string }
  const message = body.message?.trim()
  if (!message) return NextResponse.json({ error: 'message required', code: 400 }, { status: 400 })

  const admin = createAdminClient()
  const encoder = new TextEncoder()

  const stream = new ReadableStream({
    async start(controller) {
      const send = (data: Record<string, unknown>) => {
        controller.enqueue(encoder.encode(`data: ${JSON.stringify(data)}\n\n`))
      }

      try {
        const chunks = await searchChunks(message, user.id, 8)

        let threadId = body.threadId
        if (!threadId) {
          const { data: thread } = await admin
            .from('assistant_threads')
            .insert({ user_id: user.id, title: message.slice(0, 80) })
            .select()
            .single()
          threadId = thread?.id ?? null
          if (threadId) send({ type: 'threadId', threadId })
        }

        if (threadId) {
          await admin.from('assistant_messages').insert({
            thread_id: threadId,
            role: 'user',
            content: message,
            citations: [],
          })
        }

        const context = chunks.length > 0 ? buildAssistantContext(chunks) : 'No relevant papers found in your library.'
        const systemWithContext = `${ASSISTANT_SYSTEM}\n\nContext from your library:\n\n${context}`

        const { data: history } = threadId
          ? await admin
            .from('assistant_messages')
            .select('role, content')
            .eq('thread_id', threadId)
            .order('created_at')
            .limit(20)
          : { data: [] }

        const prevMessages = (history ?? [])
          .filter((m: { role: string }) => m.role !== 'system')
          .map((m: { role: string; content: string }) => ({
            role: m.role as 'user' | 'assistant',
            content: m.content,
          }))

        const claudeStream = await anthropic.messages.create({
          model: CLAUDE_MODEL,
          max_tokens: 4096,
          system: systemWithContext,
          messages: [...prevMessages, { role: 'user', content: message }],
          stream: true,
        })

        let fullText = ''
        for await (const event of claudeStream) {
          if (event.type === 'content_block_delta' && event.delta.type === 'text_delta') {
            fullText += event.delta.text
            send({ type: 'text', text: event.delta.text })
          }
        }

        const citations = extractCitations(fullText, chunks)
        send({ type: 'citations', citations })

        if (threadId) {
          await admin.from('assistant_messages').insert({
            thread_id: threadId,
            role: 'assistant',
            content: fullText,
            citations,
          })
          await admin.from('assistant_threads').update({ updated_at: new Date().toISOString() }).eq('id', threadId)
        }

        controller.enqueue(encoder.encode('data: [DONE]\n\n'))
      } catch (err) {
        send({ type: 'error', message: String(err) })
      } finally {
        controller.close()
      }
    },
  })

  return new Response(stream, {
    headers: {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      Connection: 'keep-alive',
    },
  })
}
