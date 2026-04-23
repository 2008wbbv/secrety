import { describe, it, expect, vi, beforeEach } from 'vitest'
import { testApiHandler } from 'next-test-api-route-handler'
import * as appHandler from '@/app/api/ingest/route'

const {
  mockGetUser,
  mockPaperInsert,
  mockPaperUpdate,
  mockStorageUpload,
  mockInngestSend,
  mockFetchArxiv,
  mockFetchCrossref,
} = vi.hoisted(() => ({
  mockGetUser: vi.fn(),
  mockPaperInsert: vi.fn(),
  mockPaperUpdate: vi.fn(),
  mockStorageUpload: vi.fn(),
  mockInngestSend: vi.fn(),
  mockFetchArxiv: vi.fn(),
  mockFetchCrossref: vi.fn(),
}))

vi.mock('@/lib/supabase/server', () => ({
  createClient: () => ({
    auth: { getUser: mockGetUser },
  }),
}))

vi.mock('@/lib/supabase/admin', () => ({
  createAdminClient: () => ({
    from: (table: string) => {
      if (table === 'papers') {
        return {
          insert: () => ({
            select: () => ({
              single: mockPaperInsert,
            }),
          }),
          update: () => ({
            eq: mockPaperUpdate,
          }),
        }
      }
      return {
        insert: vi.fn().mockResolvedValue({ data: null, error: null }),
      }
    },
    storage: {
      from: () => ({
        upload: mockStorageUpload,
      }),
    },
  }),
}))

vi.mock('@/inngest/client', () => ({
  inngest: { send: mockInngestSend },
}))

vi.mock('@/lib/metadata/arxiv', () => ({
  fetchArxivMetadata: mockFetchArxiv,
}))

vi.mock('@/lib/metadata/crossref', () => ({
  fetchCrossrefMetadata: mockFetchCrossref,
}))

beforeEach(() => {
  vi.clearAllMocks()
  mockInngestSend.mockResolvedValue(undefined)
})

describe('POST /api/ingest', () => {
  it('returns 401 when not authenticated', async () => {
    mockGetUser.mockResolvedValue({ data: { user: null }, error: null })

    await testApiHandler({
      appHandler,
      async test({ fetch }) {
        const res = await fetch({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ identifier: '1706.03762' }),
        })
        expect(res.status).toBe(401)
      },
    })
  })

  it('returns 400 when identifier is missing', async () => {
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
        expect(json.error).toBe('identifier required')
      },
    })
  })

  it('returns 400 for unrecognized identifier', async () => {
    mockGetUser.mockResolvedValue({ data: { user: { id: 'user-1' } }, error: null })

    await testApiHandler({
      appHandler,
      async test({ fetch }) {
        const res = await fetch({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ identifier: 'not-a-doi-or-arxiv' }),
        })
        expect(res.status).toBe(400)
        const json = await res.json()
        expect(json.error).toBe('Unrecognized DOI or arXiv ID')
      },
    })
  })

  it('ingests arxiv paper by ID', async () => {
    mockGetUser.mockResolvedValue({ data: { user: { id: 'user-1' } }, error: null })
    mockFetchArxiv.mockResolvedValue({
      title: 'Attention Is All You Need',
      authors: [{ name: 'Vaswani' }],
      year: 2017,
      abstract: 'Transformers',
      arxiv_id: '1706.03762',
      source_url: 'https://arxiv.org/pdf/1706.03762.pdf',
    })
    mockPaperInsert.mockResolvedValue({ data: { id: 'paper-uuid-1' }, error: null })
    mockPaperUpdate.mockResolvedValue({ data: null, error: null })

    await testApiHandler({
      appHandler,
      async test({ fetch }) {
        const res = await fetch({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          // detectIdentifier requires "arxiv:" prefix (bare IDs don't match the regex)
          body: JSON.stringify({ identifier: 'arxiv:1706.03762' }),
        })
        expect(res.status).toBe(200)
        const json = await res.json()
        expect(json.paperId).toBe('paper-uuid-1')
        expect(json.status).toBe('processing')
        expect(mockInngestSend).toHaveBeenCalledWith({
          name: 'paper/ingest',
          data: { paperId: 'paper-uuid-1', userId: 'user-1' },
        })
      },
    })
  })

  it('ingests arxiv paper with arxiv: prefix format', async () => {
    mockGetUser.mockResolvedValue({ data: { user: { id: 'user-1' } }, error: null })
    mockFetchArxiv.mockResolvedValue({
      title: 'Test Paper',
      authors: [],
      year: 2023,
      abstract: '',
      arxiv_id: '2301.00001',
      source_url: 'https://arxiv.org/pdf/2301.00001.pdf',
    })
    mockPaperInsert.mockResolvedValue({ data: { id: 'paper-2' }, error: null })

    await testApiHandler({
      appHandler,
      async test({ fetch }) {
        const res = await fetch({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ identifier: 'arxiv:2301.00001' }),
        })
        expect(res.status).toBe(200)
        const json = await res.json()
        expect(json.paperId).toBe('paper-2')
      },
    })
  })

  it('handles paper insert error', async () => {
    mockGetUser.mockResolvedValue({ data: { user: { id: 'user-1' } }, error: null })
    mockFetchArxiv.mockResolvedValue({
      title: 'Test', authors: [], year: null, abstract: '', arxiv_id: '0000.0001', source_url: null,
    })
    mockPaperInsert.mockResolvedValue({ data: null, error: { message: 'duplicate key' } })

    await testApiHandler({
      appHandler,
      async test({ fetch }) {
        const res = await fetch({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ identifier: 'arxiv:0000.0001' }),
        })
        expect(res.status).toBe(500)
        const json = await res.json()
        expect(json.error).toContain('duplicate key')
      },
    })
  })

  it('handles PDF file upload', async () => {
    mockGetUser.mockResolvedValue({ data: { user: { id: 'user-1' } }, error: null })
    mockPaperInsert.mockResolvedValue({ data: { id: 'paper-3' }, error: null })
    mockStorageUpload.mockResolvedValue({ data: {}, error: null })
    mockPaperUpdate.mockResolvedValue({ data: null, error: null })

    const pdfBytes = new Uint8Array([0x25, 0x50, 0x44, 0x46]) // %PDF
    const file = new File([pdfBytes], 'my-paper.pdf', { type: 'application/pdf' })
    const form = new FormData()
    form.append('file', file)

    await testApiHandler({
      appHandler,
      async test({ fetch }) {
        const res = await fetch({ method: 'POST', body: form })
        expect(res.status).toBe(200)
        const json = await res.json()
        expect(json.paperId).toBe('paper-3')
        expect(json.status).toBe('processing')
        expect(mockStorageUpload).toHaveBeenCalled()
        expect(mockInngestSend).toHaveBeenCalledWith(
          expect.objectContaining({ name: 'paper/ingest' })
        )
      },
    })
  })

  it('returns 400 when PDF form has no file', async () => {
    mockGetUser.mockResolvedValue({ data: { user: { id: 'user-1' } }, error: null })

    const form = new FormData()
    await testApiHandler({
      appHandler,
      async test({ fetch }) {
        const res = await fetch({ method: 'POST', body: form })
        expect(res.status).toBe(400)
        const json = await res.json()
        expect(json.error).toBe('No file')
      },
    })
  })
})
