import { describe, it, expect, vi, beforeEach } from 'vitest'
import { testApiHandler } from 'next-test-api-route-handler'
import * as appHandler from '@/app/api/metadata/fetch/route'

const mockGetUser = vi.fn()

vi.mock('@/lib/supabase/server', () => ({
  createClient: () => ({
    auth: { getUser: mockGetUser },
  }),
}))

vi.mock('@/lib/metadata/arxiv', () => ({
  fetchArxivMetadata: vi.fn(),
}))

vi.mock('@/lib/metadata/crossref', () => ({
  fetchCrossrefMetadata: vi.fn(),
}))

const { fetchArxivMetadata } = await import('@/lib/metadata/arxiv')
const { fetchCrossrefMetadata } = await import('@/lib/metadata/crossref')

beforeEach(() => {
  vi.clearAllMocks()
})

const fakeArxivMeta = {
  title: 'Attention Is All You Need',
  authors: [{ name: 'Vaswani' }],
  year: 2017,
  abstract: 'Transformers are great',
  arxiv_id: '1706.03762',
  source_url: 'https://arxiv.org/pdf/1706.03762.pdf',
}

describe('GET /api/metadata/fetch', () => {
  it('returns 401 when not authenticated', async () => {
    mockGetUser.mockResolvedValue({ data: { user: null }, error: null })

    await testApiHandler({
      appHandler,
      url: '/api/metadata/fetch?id=1706.03762&type=arxiv',
      async test({ fetch }) {
        const res = await fetch({ method: 'GET' })
        expect(res.status).toBe(401)
      },
    })
  })

  it('returns 400 when id param is missing', async () => {
    mockGetUser.mockResolvedValue({ data: { user: { id: 'user-1' } }, error: null })

    await testApiHandler({
      appHandler,
      url: '/api/metadata/fetch?type=arxiv',
      async test({ fetch }) {
        const res = await fetch({ method: 'GET' })
        expect(res.status).toBe(400)
        const json = await res.json()
        expect(json.error).toContain('id and type required')
      },
    })
  })

  it('returns 400 when type param is missing', async () => {
    mockGetUser.mockResolvedValue({ data: { user: { id: 'user-1' } }, error: null })

    await testApiHandler({
      appHandler,
      url: '/api/metadata/fetch?id=1706.03762',
      async test({ fetch }) {
        const res = await fetch({ method: 'GET' })
        expect(res.status).toBe(400)
      },
    })
  })

  it('fetches arxiv metadata for type=arxiv', async () => {
    mockGetUser.mockResolvedValue({ data: { user: { id: 'user-1' } }, error: null })
    vi.mocked(fetchArxivMetadata).mockResolvedValue(fakeArxivMeta)

    await testApiHandler({
      appHandler,
      url: '/api/metadata/fetch?id=1706.03762&type=arxiv',
      async test({ fetch }) {
        const res = await fetch({ method: 'GET' })
        expect(res.status).toBe(200)
        const json = await res.json()
        expect(json.meta.title).toBe('Attention Is All You Need')
        expect(json.meta.year).toBe(2017)
        expect(fetchArxivMetadata).toHaveBeenCalledWith('1706.03762')
        expect(fetchCrossrefMetadata).not.toHaveBeenCalled()
      },
    })
  })

  it('fetches crossref metadata for type=doi', async () => {
    mockGetUser.mockResolvedValue({ data: { user: { id: 'user-1' } }, error: null })
    const fakeCrossrefMeta = { title: 'DOI Paper', authors: [], year: 2020, doi: '10.1234/test', venue: 'Nature' }
    vi.mocked(fetchCrossrefMetadata).mockResolvedValue(fakeCrossrefMeta as never)

    await testApiHandler({
      appHandler,
      url: '/api/metadata/fetch?id=10.1234%2Ftest&type=doi',
      async test({ fetch }) {
        const res = await fetch({ method: 'GET' })
        expect(res.status).toBe(200)
        const json = await res.json()
        expect(json.meta.title).toBe('DOI Paper')
        expect(fetchCrossrefMetadata).toHaveBeenCalledWith('10.1234/test')
      },
    })
  })

  it('returns 500 when metadata fetch throws', async () => {
    mockGetUser.mockResolvedValue({ data: { user: { id: 'user-1' } }, error: null })
    vi.mocked(fetchArxivMetadata).mockRejectedValue(new Error('Network error'))

    await testApiHandler({
      appHandler,
      url: '/api/metadata/fetch?id=0000.00000&type=arxiv',
      async test({ fetch }) {
        const res = await fetch({ method: 'GET' })
        expect(res.status).toBe(500)
        const json = await res.json()
        expect(json.error).toContain('Network error')
      },
    })
  })
})
