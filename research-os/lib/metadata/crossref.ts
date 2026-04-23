import type { Author } from '@/types'

export interface CrossrefMetadata {
  title: string
  authors: Author[]
  year: number | null
  venue: string | null
  doi: string
  source_url: string | null
}

export async function fetchCrossrefMetadata(doi: string): Promise<CrossrefMetadata> {
  const clean = doi.replace(/^https?:\/\/doi\.org\//i, '')
  const url = `https://api.crossref.org/works/${encodeURIComponent(clean)}`
  const res = await fetch(url, {
    headers: { 'User-Agent': 'ResearchOS/1.0 (mailto:admin@example.com)' },
  })
  if (!res.ok) throw new Error(`Crossref API error: ${res.status}`)

  const json = (await res.json()) as { message: Record<string, unknown> }
  const msg = json.message

  const titleArr = msg['title'] as string[] | undefined
  const title = titleArr?.[0] ?? null
  if (!title) throw new Error('No title in Crossref response')

  const authorArr = (msg['author'] as Array<{ given?: string; family?: string }> | undefined) ?? []
  const authors: Author[] = authorArr.map((a) => ({
    name: [a.given, a.family].filter(Boolean).join(' '),
  }))

  const dateArr = msg['published'] as { 'date-parts': number[][] } | undefined
  const year = dateArr?.['date-parts']?.[0]?.[0] ?? null

  const containerTitle = msg['container-title'] as string[] | undefined
  const venue = containerTitle?.[0] ?? null

  const links = msg['link'] as Array<{ URL: string; 'content-type': string }> | undefined
  const pdfLink = links?.find((l) => l['content-type'] === 'application/pdf')?.URL ?? null

  return { title, authors, year, venue, doi: clean, source_url: pdfLink }
}
