import type { Author } from '@/types'

export interface ArxivMetadata {
  title: string
  authors: Author[]
  year: number | null
  abstract: string
  arxiv_id: string
  source_url: string
}

function parseArxivId(input: string): string {
  const match = input.match(/(?:arxiv\.org\/abs\/|arxiv:)?(\d{4}\.\d{4,5}(?:v\d+)?)/i)
  if (match) return match[1]
  return input.trim()
}

export async function fetchArxivMetadata(input: string): Promise<ArxivMetadata> {
  const id = parseArxivId(input)
  const url = `https://export.arxiv.org/api/query?id_list=${encodeURIComponent(id)}`
  const res = await fetch(url)
  if (!res.ok) throw new Error(`arXiv API error: ${res.status}`)

  const xml = await res.text()

  const title = xml.match(/<title>([\s\S]*?)<\/title>/)?.[1]?.replace(/<[^>]+>/g, '').trim() ?? null
  const published = xml.match(/<published>(.*?)<\/published>/)?.[1] ?? null
  const year = published ? new Date(published).getFullYear() : null
  const summary = xml.match(/<summary>([\s\S]*?)<\/summary>/)?.[1]?.trim() ?? ''

  const authorMatches = Array.from(xml.matchAll(/<author>[\s\S]*?<name>(.*?)<\/name>[\s\S]*?<\/author>/g))
  const authors: Author[] = authorMatches.map((m) => ({ name: m[1].trim() }))

  if (!title) throw new Error('Could not parse arXiv metadata')

  return {
    title,
    authors,
    year,
    abstract: summary,
    arxiv_id: id,
    source_url: `https://arxiv.org/pdf/${id}.pdf`,
  }
}
