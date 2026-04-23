export interface ChunkInput {
  content: string
  page_number: number
  char_start: number
  char_end: number
  token_count: number
}

const TARGET_CHARS = 3200 // ~800 tokens at 4 chars/token
const OVERLAP_CHARS = 600  // ~150 tokens

function estimateTokens(text: string): number {
  return Math.ceil(text.split(/\s+/).filter(Boolean).length * 1.3)
}

function pageForChar(charPos: number, pageBreaks: number[]): number {
  let page = 1
  for (const bp of pageBreaks) {
    if (charPos >= bp) page++
    else break
  }
  return page
}

export function chunkPages(pages: string[]): ChunkInput[] {
  const separator = '\n\n'
  const pageBreaks: number[] = []
  let pos = 0
  for (let i = 0; i < pages.length - 1; i++) {
    pos += pages[i].length + separator.length
    pageBreaks.push(pos)
  }

  const fullText = pages.join(separator)
  const chunks: ChunkInput[] = []

  let start = 0
  while (start < fullText.length) {
    const end = Math.min(start + TARGET_CHARS, fullText.length)
    const content = fullText.slice(start, end).trim()
    if (content.length > 0) {
      const midChar = start + Math.floor((end - start) / 2)
      chunks.push({
        content,
        page_number: pageForChar(midChar, pageBreaks),
        char_start: start,
        char_end: end,
        token_count: estimateTokens(content),
      })
    }
    if (end >= fullText.length) break
    start = end - OVERLAP_CHARS
  }

  return chunks
}
