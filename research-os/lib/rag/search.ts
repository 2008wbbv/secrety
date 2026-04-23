import { createClient } from '@/lib/supabase/server'
import { embedText } from '@/lib/embeddings'
import type { ChunkWithPaper, ChunkSearchResult } from '@/types'

export async function searchChunks(
  query: string,
  userId: string,
  matchCount = 8
): Promise<ChunkWithPaper[]> {
  const supabase = createClient()
  const embedding = await embedText(query)

  const { data, error } = await supabase.rpc('search_chunks', {
    query_embedding: embedding,
    query_text: query,
    match_count: matchCount,
    user_id_input: userId,
  })

  if (error) throw new Error(`search_chunks RPC failed: ${error.message}`)

  const results = (data as ChunkSearchResult[]) ?? []

  const paperIds = Array.from(new Set(results.map((r) => r.paper_id)))
  const { data: papers, error: papersError } = await supabase
    .from('papers')
    .select('id, title, authors, year')
    .in('id', paperIds)

  if (papersError) throw new Error(`papers fetch failed: ${papersError.message}`)

  const paperMap = new Map((papers ?? []).map((p) => [p.id, p]))

  return results.map((r) => ({
    ...r,
    paper: paperMap.get(r.paper_id) ?? { id: r.paper_id, title: null, authors: [], year: null },
  }))
}
