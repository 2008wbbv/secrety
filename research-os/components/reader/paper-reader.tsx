'use client'

import { useState } from 'react'
import Link from 'next/link'
import { ArrowLeft } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { PDFViewer } from '@/components/reader/pdf-viewer'
import { MetadataPanel } from '@/components/reader/metadata-panel'
import { NotesPanel } from '@/components/reader/notes-panel'
import { createClient } from '@/lib/supabase/client'
import type { Paper, Note } from '@/types'

interface Props {
  paper: Paper
  initialNotes: Note[]
  userId: string
}

export function PaperReader({ paper, initialNotes, userId }: Props) {
  const supabase = createClient()
  const [pdfUrl, setPdfUrl] = useState<string | null>(null)

  if (paper.storage_path && !pdfUrl) {
    supabase.storage
      .from('papers')
      .createSignedUrl(paper.storage_path, 3600)
      .then(({ data }) => { if (data) setPdfUrl(data.signedUrl) })
  }

  return (
    <div className="flex h-full">
      <div className="flex-1 flex flex-col overflow-hidden">
        <div className="flex items-center gap-2 border-b px-4 py-2 shrink-0">
          <Button variant="ghost" size="sm" asChild>
            <Link href="/library">
              <ArrowLeft className="h-4 w-4 mr-1" />
              Library
            </Link>
          </Button>
          <span className="text-sm font-medium truncate">{paper.title ?? 'Paper'}</span>
        </div>

        <div className="flex-1 overflow-hidden">
          {pdfUrl ? (
            <PDFViewer url={pdfUrl} />
          ) : (
            <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
              {paper.status === 'processing' ? 'Processing PDF...' : 'No PDF available.'}
            </div>
          )}
        </div>
      </div>

      <div className="w-72 border-l flex flex-col overflow-hidden">
        <Tabs defaultValue="info" className="flex flex-col h-full">
          <TabsList className="mx-4 mt-2 shrink-0">
            <TabsTrigger value="info" className="flex-1 text-xs">Info</TabsTrigger>
            <TabsTrigger value="notes" className="flex-1 text-xs">Notes</TabsTrigger>
          </TabsList>
          <TabsContent value="info" className="flex-1 overflow-hidden mt-0">
            <MetadataPanel paper={paper} />
          </TabsContent>
          <TabsContent value="notes" className="flex-1 overflow-hidden mt-0">
            <NotesPanel paperId={paper.id} userId={userId} initialNotes={initialNotes} />
          </TabsContent>
        </Tabs>
      </div>
    </div>
  )
}
