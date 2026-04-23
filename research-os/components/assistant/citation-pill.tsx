'use client'

import Link from 'next/link'
import type { Citation } from '@/types'

interface CitationPillProps {
  citation: Citation
}

export function CitationPill({ citation }: CitationPillProps) {
  return (
    <Link
      href={`/paper/${citation.paper_id}${citation.page_number ? `?page=${citation.page_number}` : ''}`}
      title={citation.paper_title ?? undefined}
      className="inline-flex items-center gap-1 rounded bg-primary/10 px-1.5 py-0.5 text-xs font-medium text-primary hover:bg-primary/20 transition-colors cursor-pointer"
    >
      [{citation.index}]
    </Link>
  )
}
