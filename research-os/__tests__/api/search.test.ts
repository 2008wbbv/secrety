import { describe, it, expect, vi, beforeEach } from 'vitest'
import { testApiHandler } from 'next-test-api-route-handler'
import * as appHandler from '@/app/api/search/route'

const mockGetUser = vi.fn()
const mockRpc = vi.fn()
const mockFrom = vi.fn()

vi.mock('@/lib/supabase/server', () => ({
  createClient: () => ({
    auth: { getUser: mockGetUser },
    rpc: mockRpc,
    from: mockFrom,
  }),
}))

vi.mock('@/lib/embeddings', () => ({
  embedText: vi.fn().mockResolvedValue(Array(1536).fill(0.1)),
}))

vi.mock('@/lib/rag/search', () => ({
  searchChunks: vi.fn(),
}))

const { searchChunks } = await import('@/lib/rag/search')

beforeEach(() => {
  vi.clearAllMocks()
})

describe('POST /api/search', () => {
  it('returns 401 when not authenticated', async () => {
    mockGetUser.mockResolvedValue({ data: { user: null }, error: null })

    await testApiHandler({
      appHandler,
      async test({ fetch }) {
        const res = await fetch({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ query: 'transformer attention' }),
        })
        expect(res.status).toBe(401)
        const json = await res.json()
        expect(json.error).toBe('Unauthorized')
      },
    })
  })

  it('returns 400 when query is missing', async () => {
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
        expect(json.error).toBe('query required')
      },
    })
  })

  it('returns 400 when query is empty string', async () => {
    mockGetUser.mockResolvedValue({ data: { user: { id: 'user-1' } }, error: null })

    await testApiHandler({
      appHandler,
      async test({ fetch }) {
        const res = await fetch({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ query: '   ' }),
        })
        expect(res.status).toBe(400)
      },
    })
  })

  it('returns search results on success', async () => {
    mockGetUser.mockResolvedValue({ data: { user: { id: 'user-1' } }, error: null })
    const fakeResults = [
      { id: 'chunk-1', paper_id: 'paper-1', content: 'transformer text', page_number: 2, paper: { id: 'paper-1', title: 'Test Paper', authors: [], year: 2024 } },
    ]
    vi.mocked(searchChunks).mockResolvedValue(fakeResults as never)

    await testApiHandler({
      appHandler,
      async test({ fetch }) {
        const res = await fetch({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ query: 'transformer attention' }),
        })
        expect(res.status).toBe(200)
        const json = await res.json()
        expect(json.results).toHaveLength(1)
        expect(json.results[0].content).toBe('transformer text')
      },
    })
  })

  it('returns 500 when searchChunks throws', async () => {
    mockGetUser.mockResolvedValue({ data: { user: { id: 'user-1' } }, error: null })
    vi.mocked(searchChunks).mockRejectedValue(new Error('DB error'))

    await testApiHandler({
      appHandler,
      async test({ fetch }) {
        const res = await fetch({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ query: 'anything' }),
        })
        expect(res.status).toBe(500)
        const json = await res.json()
        expect(json.error).toContain('DB error')
      },
    })
  })
})
