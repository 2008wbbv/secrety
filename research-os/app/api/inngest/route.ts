import { serve } from 'inngest/next'
import { inngest } from '@/inngest/client'
import { ingestPaper } from '@/inngest/functions/ingest-paper'

export const { GET, POST, PUT } = serve({
  client: inngest,
  functions: [ingestPaper],
})
