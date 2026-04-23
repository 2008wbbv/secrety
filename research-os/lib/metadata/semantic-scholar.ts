import type { Author } from '@/types'

export interface SemanticScholarMetadata {
  title: string
  authors: Author[]
  year: number | null
  venue: string | null
  semantic_scholar_id: string
  doi: string | null
  source_url: string | null
  abstract: string | null
}

const BASE = 'https://api.semanticscholar.org/graph/v1'
const FIELDS = 'title,authors,year,venue,externalIds,openAccessPdf,abstract'

export async function fetchByDOI(doi: string): Promise<SemanticScholarMetadata | null> {
  return fetchSemanticScholar(`DOI:${doi}`)
}

export async function fetchByArxivId(arxivId: string): Promise<SemanticScholarMetadata | null> {
  return fetchSemanticScholar(`ARXIV:${arxivId}`)
}

async function fetchSemanticScholar(id: string): Promise<SemanticScholarMetadata | null> {
  const apiKey = process.env.SEMANTIC_SCHOLAR_API_KEY
  const headers: HeadersInit = apiKey ? { 'x-api-key': apiKey } : {}

  const res = await fetch(`${BASE}/paper/${encodeURIComponent(id)}?fields=${FIELDS}`, { headers })
  if (!res.ok) return null

  const data = (await res.json()) as Record<string, unknown>

  const authors: Author[] = ((data['authors'] as Array<{ name: string }>) ?? []).map((a) => ({
    name: a.name,
  }))

  const externalIds = data['externalIds'] as Record<string, string> | undefined
  const pdfObj = data['openAccessPdf'] as { url?: string } | undefined

  return {
    title: (data['title'] as string) ?? 'Untitled',
    authors,
    year: (data['year'] as number | null) ?? null,
    venue: (data['venue'] as string | null) ?? null,
    semantic_scholar_id: (data['paperId'] as string) ?? '',
    doi: externalIds?.['DOI'] ?? null,
    source_url: pdfObj?.url ?? null,
    abstract: (data['abstract'] as string | null) ?? null,
  }
}
