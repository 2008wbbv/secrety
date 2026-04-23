import { inngest } from '@/inngest/client'
import { createAdminClient } from '@/lib/supabase/admin'
import { extractPDFText, isTextSufficient } from '@/lib/pdf/extract'
import { chunkPages } from '@/lib/pdf/chunk'
import { embedBatch } from '@/lib/embeddings'
import { complete } from '@/lib/llm/claude'
import { SUMMARIZE_SYSTEM, buildSummarizePrompt } from '@/lib/llm/prompts/summarize'
import type { IngestPayload } from '@/types'

export const ingestPaper = inngest.createFunction(
  { id: 'ingest-paper', retries: 2, triggers: { event: 'paper/ingest' } },
  async ({ event, step }) => {
    const { paperId, userId } = event.data as IngestPayload

    const paper = await step.run('fetch-paper', async () => {
      const supabase = createAdminClient()
      const { data, error } = await supabase
        .from('papers')
        .select('id, title, storage_path, source_url')
        .eq('id', paperId)
        .single()
      if (error) throw new Error(`Paper ${paperId} not found: ${error.message}`)
      return data as { id: string; title: string | null; storage_path: string | null; source_url: string | null }
    })

    const pdfBuffer = await step.run('download-pdf', async () => {
      const supabase = createAdminClient()
      if (paper.storage_path) {
        const { data } = await supabase.storage.from('papers').download(paper.storage_path)
        if (data) return Array.from(new Uint8Array(await data.arrayBuffer()))
      }
      if (paper.source_url) {
        const res = await fetch(paper.source_url)
        if (res.ok) return Array.from(new Uint8Array(await res.arrayBuffer()))
      }
      throw new Error('No PDF source available')
    })

    const extracted = await step.run('extract-text', async () => {
      const buffer = new Uint8Array(pdfBuffer).buffer
      const result = await extractPDFText(buffer)
      if (!isTextSufficient(result.fullText)) {
        throw new Error('Extracted text is too short. Scanned PDF OCR not yet supported.')
      }
      return result
    })

    await step.run('update-page-count', async () => {
      const supabase = createAdminClient()
      await supabase.from('papers').update({ page_count: extracted.totalPages }).eq('id', paperId)
    })

    const rawChunks = await step.run('chunk-text', async () => {
      return chunkPages(extracted.pages)
    })

    const embeddings = await step.run('embed-chunks', async () => {
      return embedBatch(rawChunks.map((c) => c.content))
    })

    await step.run('save-chunks', async () => {
      const supabase = createAdminClient()
      const rows = rawChunks.map((c, i) => ({
        paper_id: paperId,
        user_id: userId,
        chunk_index: i,
        content: c.content,
        page_number: c.page_number,
        char_start: c.char_start,
        char_end: c.char_end,
        token_count: c.token_count,
        embedding: embeddings[i],
      }))
      const BATCH = 50
      for (let i = 0; i < rows.length; i += BATCH) {
        const { error } = await supabase.from('chunks').insert(rows.slice(i, i + BATCH))
        if (error) throw new Error(`Chunk insert failed: ${error.message}`)
      }
    })

    const summary = await step.run('summarize', async () => {
      return complete(SUMMARIZE_SYSTEM, buildSummarizePrompt(paper.title, extracted.fullText))
    })

    await step.run('finalize', async () => {
      const supabase = createAdminClient()
      await supabase.from('papers').update({ status: 'ready', summary }).eq('id', paperId)
    })

    return { paperId, chunks: rawChunks.length, summary }
  }
)
