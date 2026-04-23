import { describe, it, expect, vi, beforeEach } from 'vitest'
import { testApiHandler } from 'next-test-api-route-handler'
import * as appHandler from '@/app/api/assistant/route'

const { mockGetUser, mockSearchChunks, mockInsertThread, mockInsertMessage, mockSelectMessages, mockUpdateThread } = vi.hoisted(() => ({
  mockGetUser: vi.fn(),
  mockSearchChunks: vi.fn(),
  mockInsertThread: vi.fn(),
  mockInsertMessage: vi.fn(),
  mockSelectMessages: vi.fn(),
  mockUpdateThread: vi.fn(),
}))

vi.mock('@/lib/supabase/server', () => ({
  createClient: () => ({
    auth: { getUser: mockGetUser },
  }),
}))

vi.mock('@/lib/supabase/admin', () => ({
  createAdminClient: () => ({
    from: (table: string) => {
      if (table === 'assistant_threads') {
        return {
          insert: () => ({
            select: () => ({ single: mockInsertThread }),
          }),
          update: () => ({ eq: mockUpdateThread }),
        }
      }
      if (table === 'assistant_messages') {
        return {
          insert: mockInsertMessage,
          select: () => ({
            eq: () => ({ order: () => ({ limit: mockSelectMessages }) }),
          }),
        }
      }
      return {}
    },
  }),
}))

vi.mock('@/lib/rag/search', () => ({
  searchChunks: mockSearchChunks,
}))

beforeEach(() => {
  vi.clearAllMocks()
  // STUB_AI=true is set in vitest.config.ts so no real Anthropic calls happen
  mockSearchChunks.mockResolvedValue([])
  mockInsertThread.mockResolvedValue({ data: { id: 'thread-1' }, error: null })
  mockInsertMessage.mockResolvedValue({ data: null, error: null })
  mockSelectMessages.mockResolvedValue({ data: [], error: null })
  mockUpdateThread.mockResolvedValue({ data: null, error: null })
})

function collectSSE(stream: ReadableStream<Uint8Array>): Promise<string> {
  const reader = stream.getReader()
  const decoder = new TextDecoder()
  let result = ''
  return new Promise((resolve, reject) => {
    function read() {
      reader.read().then(({ done, value }) => {
        if (done) { resolve(result); return }
        result += decoder.decode(value)
        read()
      }).catch(reject)
    }
    read()
  })
}

describe('POST /api/assistant', () => {
  it('returns 401 when not authenticated', async () => {
    mockGetUser.mockResolvedValue({ data: { user: null }, error: null })

    await testApiHandler({
      appHandler,
      async test({ fetch }) {
        const res = await fetch({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message: 'hello' }),
        })
        expect(res.status).toBe(401)
      },
    })
  })

  it('returns 400 when message is missing', async () => {
    mockGetUser.mockResolvedValue({ data: { user: { id: 'user-1' } }, error: null })

    await testApiHandler({
      appHandler,
      async test({ fetch }) {
        const res = await fetch({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({}),
        })
        expect(res.status).toBe(400)
        const json = await res.json()
        expect(json.error).toBe('message required')
      },
    })
  })

  it('streams SSE response with text events and [DONE]', async () => {
    mockGetUser.mockResolvedValue({ data: { user: { id: 'user-1' } }, error: null })

    await testApiHandler({
      appHandler,
      async test({ fetch }) {
        const res = await fetch({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message: 'What is attention mechanism?' }),
        })

        expect(res.status).toBe(200)
        expect(res.headers.get('content-type')).toContain('text/event-stream')

        const raw = await collectSSE(res.body!)

        expect(raw).toContain('"type":"text"')
        expect(raw).toContain('"type":"citations"')
        expect(raw).toContain('[DONE]')
      },
    })
  })

  it('emits threadId event when no threadId provided', async () => {
    mockGetUser.mockResolvedValue({ data: { user: { id: 'user-1' } }, error: null })

    await testApiHandler({
      appHandler,
      async test({ fetch }) {
        const res = await fetch({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message: 'Tell me about BERT' }),
        })

        const raw = await collectSSE(res.body!)
        expect(raw).toContain('"type":"threadId"')
        expect(raw).toContain('thread-1')
      },
    })
  })

  it('does not emit threadId when one is provided', async () => {
    mockGetUser.mockResolvedValue({ data: { user: { id: 'user-1' } }, error: null })

    await testApiHandler({
      appHandler,
      async test({ fetch }) {
        const res = await fetch({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message: 'Follow-up question', threadId: 'existing-thread' }),
        })

        const raw = await collectSSE(res.body!)
        expect(raw).not.toContain('"type":"threadId"')
      },
    })
  })

  it('extracts citations from stub response', async () => {
    mockGetUser.mockResolvedValue({ data: { user: { id: 'user-1' } }, error: null })
    // STUB_ASSISTANT_RESPONSE contains [1] and [2] references
    mockSearchChunks.mockResolvedValue([
      { id: 'c1', paper_id: 'p1', content: 'chunk 1', page_number: 1, paper: { id: 'p1', title: 'Paper One', authors: [], year: 2023 } },
      { id: 'c2', paper_id: 'p2', content: 'chunk 2', page_number: 3, paper: { id: 'p2', title: 'Paper Two', authors: [], year: 2022 } },
    ])

    await testApiHandler({
      appHandler,
      async test({ fetch }) {
        const res = await fetch({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message: 'Summarize findings' }),
        })

        const raw = await collectSSE(res.body!)
        const citationsLine = raw.split('\n').find((l) => l.includes('"type":"citations"'))
        expect(citationsLine).toBeDefined()

        const parsed = JSON.parse(citationsLine!.replace('data: ', ''))
        expect(parsed.citations.length).toBeGreaterThan(0)
        expect(parsed.citations[0].paper_title).toBe('Paper One')
      },
    })
  })
})
