import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fetchArxivMetadata } from '@/lib/metadata/arxiv'

const SAMPLE_XML = `<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>Attention Is All You Need</title>
    <published>2017-06-12T00:00:00Z</published>
    <summary>The dominant sequence transduction models are based on complex recurrent or convolutional neural networks.</summary>
    <author><name>Ashish Vaswani</name></author>
    <author><name>Noam Shazeer</name></author>
    <author><name>Niki Parmar</name></author>
  </entry>
</feed>`

beforeEach(() => {
  vi.restoreAllMocks()
})

describe('fetchArxivMetadata', () => {
  it('parses title, year, abstract, and authors from XML', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      text: () => Promise.resolve(SAMPLE_XML),
    }))

    const meta = await fetchArxivMetadata('1706.03762')
    expect(meta.title).toBe('Attention Is All You Need')
    expect(meta.year).toBe(2017)
    expect(meta.abstract).toContain('sequence transduction')
    expect(meta.authors).toHaveLength(3)
    expect(meta.authors[0].name).toBe('Ashish Vaswani')
    expect(meta.arxiv_id).toBe('1706.03762')
    expect(meta.source_url).toBe('https://arxiv.org/pdf/1706.03762.pdf')
  })

  it('extracts arXiv ID from full URL', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      text: () => Promise.resolve(SAMPLE_XML),
    }))

    const meta = await fetchArxivMetadata('https://arxiv.org/abs/1706.03762')
    expect(meta.arxiv_id).toBe('1706.03762')
  })

  it('extracts arXiv ID from arxiv: prefix', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      text: () => Promise.resolve(SAMPLE_XML),
    }))

    const meta = await fetchArxivMetadata('arxiv:1706.03762')
    expect(meta.arxiv_id).toBe('1706.03762')
  })

  it('throws on non-ok HTTP response', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 503 }))
    await expect(fetchArxivMetadata('1234.56789')).rejects.toThrow('arXiv API error: 503')
  })

  it('throws when XML has no title', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      text: () => Promise.resolve('<feed><entry><summary>no title here</summary></entry></feed>'),
    }))
    await expect(fetchArxivMetadata('0000.00000')).rejects.toThrow('Could not parse arXiv metadata')
  })

  it('calls the correct arXiv API URL', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      text: () => Promise.resolve(SAMPLE_XML),
    })
    vi.stubGlobal('fetch', mockFetch)

    await fetchArxivMetadata('1706.03762')
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining('export.arxiv.org/api/query?id_list=1706.03762')
    )
  })

  it('returns null year when published date is missing', async () => {
    const xmlNoDate = SAMPLE_XML.replace(/<published>.*?<\/published>/, '')
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      text: () => Promise.resolve(xmlNoDate),
    }))

    const meta = await fetchArxivMetadata('1706.03762')
    expect(meta.year).toBeNull()
  })
})
