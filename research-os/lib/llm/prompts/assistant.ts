import type { ChunkWithPaper } from '@/types'

export const ASSISTANT_SYSTEM = `You are a research assistant helping users understand scientific literature from their personal library. Answer questions based only on the provided context chunks. Always cite your sources using [N] notation where N is the chunk number. If information is not in the provided chunks, say so explicitly. Be precise, concise, and scholarly.`

export function buildAssistantContext(chunks: ChunkWithPaper[]): string {
  return chunks
    .map((c, i) => {
      const authors =
        c.paper.authors.length > 0 ? c.paper.authors.map((a) => a.name).join(', ') : 'Unknown'
      const year = c.paper.year ?? 'n.d.'
      const title = c.paper.title ?? 'Untitled'
      return `[${i + 1}] "${title}" (${authors}, ${year})\nPage ${c.page_number ?? '?'}:\n${c.content}`
    })
    .join('\n\n---\n\n')
}
