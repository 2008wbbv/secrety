import { inngest } from '@/inngest/client'
import { createAdminClient } from '@/lib/supabase/admin'
import { extractPDFText, isTextSufficient } from '@/lib/pdf/extract'
import { chunkPages } from '@/lib/pdf/chunk'
import { embedBatch } from '@/lib/embeddings'
import { complete } from '@/lib/llm/claude'
import { SUMMARIZE_SYSTEM, buildSummarizePrompt } from '@/lib/llm/prompts/summarize'
import type { IngestPayload } from '@/types'

export const ingestPaper = inngest.createFunction(
  { id: 'ingest-paper', retries: 2 },
  { event: 'paper/ingest' },
  async ({ event }) => {
    const { paperId, userId } = event.data as IngestPayload
    const supabase = createAdminClient()

    const { data: paper, error: paperError } = await supabase
      .from('papers')
      .select('*')
      .eq('id', paperId)
      .single()

    if (paperError || !paper) {
      throw new Error(`Paper ${paperId} not found`)
    }

    try {
      let pdfBuffer: ArrayBuffer | null = null

      if (paper['storage_path']) {
        const { data: storageData } = await supabase.storage
          .from('papers')
          .download(paper['storage_path'] as string)
        if (storageData) pdfBuffer = await storageData.arrayBuffer()
      } else if (paper['source_url']) {
        const res = await fetch(paper['source_url'] as string)
        if (res.ok) pdfBuffer = await res.arrayBuffer()
      }

      if (!pdfBuffer) {
        await supabase.from('papers').update({ status: 'failed', error_message: 'No PDF available' }).eq('id', paperId)
        return
      }

      const extracted = await extractPDFText(pdfBuffer)

      if (!isTextSufficient(extracted.fullText)) {
        await supabase.from('papers').update({ status: 'failed', error_message: 'PDF text extraction insufficient. Scanned PDF OCR not yet configured.' }).eq('id', paperId)
        return
      }

      await supabase.from('papers').update({ page_count: extracted.totalPages }).eq('id', paperId)

      const rawChunks = chunkPages(extracted.pages)
      const texts = rawChunks.map((c) => c.content)
      const embeddings = await embedBatch(texts)

      const chunkRows = rawChunks.map((c, i) => ({
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
      for (let i = 0; i < chunkRows.length; i += BATCH) {
        const batch = chunkRows.slice(i, i + BATCH)
        const { error } = await supabase.from('chunks').insert(batch)
        if (error) throw new Error(`Chunk insert failed: ${error.message}`)
      }

      const summary = await complete(
        SUMMARIZE_SYSTEM,
        buildSummarizePrompt(paper['title'] as string | null, extracted.fullText)
      )

      await supabase
        .from('papers')
        .update({ status: 'ready', summary })
        .eq('id', paperId)
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err)
      await supabase
        .from('papers')
        .update({ status: 'failed', error_message: message })
        .eq('id', paperId)
      throw err
    }
  }
)
