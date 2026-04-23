import { describe, it, expect, vi } from 'vitest'
import { InngestTestEngine } from '@inngest/test'
import { ingestPaper } from '@/inngest/functions/ingest-paper'

const { mockAdminFrom, mockSingle, mockUpdateEq, mockInsert } = vi.hoisted(() => ({
  mockAdminFrom: vi.fn(),
  mockSingle: vi.fn(),
  mockUpdateEq: vi.fn(),
  mockInsert: vi.fn(),
}))

vi.mock('@/lib/supabase/admin', () => ({
  createAdminClient: () => ({
    from: mockAdminFrom,
    storage: { from: () => ({ download: vi.fn() }) },
  }),
}))

vi.mock('@/lib/pdf/extract', () => ({
  extractPDFText: vi.fn(),
  isTextSufficient: vi.fn().mockReturnValue(true),
}))

vi.mock('@/lib/pdf/chunk', () => ({
  chunkPages: vi.fn(),
}))

vi.mock('@/lib/embeddings', () => ({
  embedBatch: vi.fn(),
}))

vi.mock('@/lib/llm/claude', () => ({
  complete: vi.fn(),
  SUMMARIZE_SYSTEM: 'Summarize this paper.',
}))

vi.mock('@/lib/llm/prompts/summarize', () => ({
  SUMMARIZE_SYSTEM: 'Summarize this paper.',
  buildSummarizePrompt: vi.fn().mockReturnValue('Summarize: Test Paper\n\nFull text...'),
}))

const fakePaper = { id: 'paper-1', title: 'Test Paper', storage_path: null, source_url: 'https://example.com/paper.pdf' }
const fakePdfBuffer = Array.from({ length: 200 }, (_, i) => i % 256)
const fakeExtracted = {
  fullText: 'This is the full text of the paper. '.repeat(50),
  pages: ['Page 1 content here.', 'Page 2 content here.'],
  totalPages: 2,
}
const fakeChunks = [
  { content: 'Chunk one content', page_number: 1, char_start: 0, char_end: 100, token_count: 20 },
  { content: 'Chunk two content', page_number: 2, char_start: 80, char_end: 200, token_count: 18 },
]
const fakeEmbeddings = [Array(1536).fill(0.1), Array(1536).fill(0.2)]
const fakeSummary = 'This paper presents a novel approach to machine learning.'

const ALL_STEPS = [
  { id: 'fetch-paper', handler: async () => fakePaper },
  { id: 'download-pdf', handler: async () => fakePdfBuffer },
  { id: 'extract-text', handler: async () => fakeExtracted },
  { id: 'update-page-count', handler: async () => undefined },
  { id: 'chunk-text', handler: async () => fakeChunks },
  { id: 'embed-chunks', handler: async () => fakeEmbeddings },
  { id: 'save-chunks', handler: async () => undefined },
  { id: 'summarize', handler: async () => fakeSummary },
  { id: 'finalize', handler: async () => undefined },
]

// Create a fresh engine per test — the engine caches step results and must not be shared
function makeEngine() {
  return new InngestTestEngine({ function: ingestPaper })
}

describe('ingest-paper Inngest function', () => {
  it('runs all steps and returns paperId, chunks count, summary', async () => {
    const { result } = await makeEngine().execute({
      events: [{ name: 'paper/ingest', data: { paperId: 'paper-1', userId: 'user-1' } }],
      steps: ALL_STEPS,
    })

    expect(result).toEqual({
      paperId: 'paper-1',
      chunks: 2,
      summary: fakeSummary,
    })
  })

  it('returns correct chunk count for variable chunk sizes', async () => {
    const manyChunks = Array.from({ length: 10 }, (_, i) => ({
      content: `Chunk ${i}`,
      page_number: 1,
      char_start: i * 100,
      char_end: (i + 1) * 100,
      token_count: 15,
    }))

    const { result } = await makeEngine().execute({
      events: [{ name: 'paper/ingest', data: { paperId: 'paper-2', userId: 'user-1' } }],
      steps: [
        ...ALL_STEPS.slice(0, 4),
        { id: 'chunk-text', handler: async () => manyChunks },
        { id: 'embed-chunks', handler: async () => Array.from({ length: 10 }, () => Array(1536).fill(0)) },
        { id: 'save-chunks', handler: async () => undefined },
        { id: 'summarize', handler: async () => 'Short summary' },
        { id: 'finalize', handler: async () => undefined },
      ],
    })

    expect(result).toEqual({
      paperId: 'paper-2',
      chunks: 10,
      summary: 'Short summary',
    })
  })

  it('uses userId from event data in save-chunks', async () => {
    const savedRows: unknown[] = []
    mockAdminFrom.mockImplementation((table: string) => {
      if (table === 'chunks') {
        return {
          insert: (rows: unknown[]) => {
            savedRows.push(...rows)
            return Promise.resolve({ data: null, error: null })
          },
        }
      }
      return {
        update: () => ({ eq: mockUpdateEq.mockResolvedValue({ data: null, error: null }) }),
        insert: mockInsert.mockReturnValue({ select: () => ({ single: mockSingle }) }),
      }
    })

    // Run only up to save-chunks (first 7 steps mocked, save-chunks runs real)
    const stepsWithRealSave = [
      { id: 'fetch-paper', handler: async () => fakePaper },
      { id: 'download-pdf', handler: async () => fakePdfBuffer },
      { id: 'extract-text', handler: async () => fakeExtracted },
      { id: 'update-page-count', handler: async () => undefined },
      { id: 'chunk-text', handler: async () => fakeChunks },
      { id: 'embed-chunks', handler: async () => fakeEmbeddings },
      // save-chunks runs real handler
      { id: 'summarize', handler: async () => fakeSummary },
      { id: 'finalize', handler: async () => undefined },
    ]

    await makeEngine().execute({
      events: [{ name: 'paper/ingest', data: { paperId: 'paper-1', userId: 'user-42' } }],
      steps: stepsWithRealSave,
    })

    // Verify each saved row has the correct userId
    expect(savedRows.length).toBe(2)
    for (const row of savedRows as Array<{ user_id: string }>) {
      expect(row.user_id).toBe('user-42')
    }
  })

  it('returns no-error result when function succeeds', async () => {
    const output = await makeEngine().execute({
      events: [{ name: 'paper/ingest', data: { paperId: 'paper-1', userId: 'user-1' } }],
      steps: ALL_STEPS,
    })

    expect(output.error).toBeUndefined()
    expect(output.result).toBeDefined()
    expect(output.ctx).toBeDefined()
    expect(output.state).toBeDefined()
  })
})
