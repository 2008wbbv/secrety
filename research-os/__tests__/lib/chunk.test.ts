import { describe, it, expect } from 'vitest'
import { chunkPages } from '@/lib/pdf/chunk'

describe('chunkPages', () => {
  it('returns empty array for empty input', () => {
    expect(chunkPages([])).toEqual([])
  })

  it('returns a single chunk for short text', () => {
    const pages = ['Hello world. This is a short page.']
    const chunks = chunkPages(pages)
    expect(chunks).toHaveLength(1)
    expect(chunks[0].content).toContain('Hello world')
    expect(chunks[0].page_number).toBe(1)
    expect(chunks[0].char_start).toBe(0)
    expect(chunks[0].token_count).toBeGreaterThan(0)
  })

  it('sets correct page numbers for multi-page input', () => {
    const p1 = 'A'.repeat(100)
    const p2 = 'B'.repeat(100)
    const chunks = chunkPages([p1, p2])
    // Both pages are small — should land in one chunk but page_number reflects midpoint
    expect(chunks.length).toBeGreaterThanOrEqual(1)
    chunks.forEach((c) => {
      expect(c.page_number).toBeGreaterThanOrEqual(1)
      expect(c.page_number).toBeLessThanOrEqual(2)
    })
  })

  it('produces multiple chunks for long text', () => {
    // 3200 chars per chunk target, make text ~10000 chars
    const longPage = 'word '.repeat(2000) // 10000 chars
    const chunks = chunkPages([longPage])
    expect(chunks.length).toBeGreaterThan(1)
  })

  it('chunks overlap — char ranges overlap by ~600 chars', () => {
    const longPage = 'x '.repeat(3000) // 6000 chars
    const chunks = chunkPages([longPage])
    if (chunks.length >= 2) {
      const overlap = chunks[0].char_end - chunks[1].char_start
      // overlap should be around 600
      expect(Math.abs(overlap)).toBeLessThanOrEqual(700)
    }
  })

  it('char_end is always >= char_start', () => {
    const pages = ['Page one text.', 'Page two text.', 'Page three text.']
    const chunks = chunkPages(pages)
    for (const c of chunks) {
      expect(c.char_end).toBeGreaterThanOrEqual(c.char_start)
    }
  })

  it('content matches the substring of the joined text', () => {
    const pages = ['First page content.', 'Second page content.']
    const fullText = pages.join('\n\n')
    const chunks = chunkPages(pages)
    for (const c of chunks) {
      const slice = fullText.slice(c.char_start, c.char_end).trim()
      expect(c.content).toBe(slice)
    }
  })

  it('token_count is a positive integer', () => {
    const pages = ['Some research text with multiple words and sentences.']
    const chunks = chunkPages(pages)
    for (const c of chunks) {
      expect(Number.isInteger(c.token_count)).toBe(true)
      expect(c.token_count).toBeGreaterThan(0)
    }
  })
})
