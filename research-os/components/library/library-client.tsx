'use client'

import { useEffect, useState } from 'react'
import { LayoutGrid, List, Plus, Search } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { ScrollArea } from '@/components/ui/scroll-area'
import { PaperCard } from '@/components/library/paper-card'
import { UploadArea } from '@/components/library/upload-area'
import { DOIInput } from '@/components/library/doi-input'
import { EmptyState } from '@/components/library/empty-state'
import { ProcessingCard } from '@/components/library/processing-card'
import { createClient } from '@/lib/supabase/client'
import type { Paper, ReadingStatus } from '@/types'

interface Props {
  initialPapers: Paper[]
  userId: string
}

export function LibraryClient({ initialPapers, userId }: Props) {
  const [papers, setPapers] = useState<Paper[]>(initialPapers)
  const [view, setView] = useState<'grid' | 'list'>('grid')
  const [showUpload, setShowUpload] = useState(false)
  const [query, setQuery] = useState('')
  const supabase = createClient()

  useEffect(() => {
    const channel = supabase
      .channel('papers-status')
      .on(
        'postgres_changes',
        { event: 'UPDATE', schema: 'public', table: 'papers', filter: `user_id=eq.${userId}` },
        (payload) => {
          setPapers((prev) =>
            prev.map((p) => (p.id === payload.new['id'] ? { ...p, ...(payload.new as Paper) } : p))
          )
        }
      )
      .on(
        'postgres_changes',
        { event: 'INSERT', schema: 'public', table: 'papers', filter: `user_id=eq.${userId}` },
        (payload) => {
          setPapers((prev) => [payload.new as Paper, ...prev])
        }
      )
      .subscribe()

    return () => { supabase.removeChannel(channel) }
  }, [supabase, userId])

  const handleStatusChange = (id: string, status: ReadingStatus) => {
    setPapers((prev) => prev.map((p) => (p.id === id ? { ...p, reading_status: status } : p)))
  }

  const handleAdded = (paperId: string) => {
    // realtime channel will pick up the insert
    void paperId
  }

  const processing = papers.filter((p) => p.status === 'processing' || p.status === 'failed')
  const ready = papers.filter((p) => p.status === 'ready')

  const filtered = query
    ? ready.filter(
        (p) =>
          p.title?.toLowerCase().includes(query.toLowerCase()) ||
          p.authors.some((a) => a.name.toLowerCase().includes(query.toLowerCase()))
      )
    : ready

  if (papers.length === 0 && !showUpload) {
    return <EmptyState onUpload={() => setShowUpload(true)} />
  }

  return (
    <div className="flex flex-col flex-1 overflow-hidden">
      <div className="border-b px-6 py-3 space-y-3">
        {processing.length > 0 && <ProcessingCard papers={processing} />}

        {showUpload && (
          <div className="space-y-2">
            <UploadArea onUploaded={handleAdded} onClose={() => setShowUpload(false)} />
            <DOIInput onAdded={handleAdded} />
          </div>
        )}

        <div className="flex items-center gap-2">
          <div className="relative flex-1 max-w-sm">
            <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Filter by title or author"
              className="pl-8"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
          <div className="flex items-center gap-1 ml-auto">
            <Button
              variant={view === 'grid' ? 'secondary' : 'ghost'}
              size="icon"
              onClick={() => setView('grid')}
            >
              <LayoutGrid className="h-4 w-4" />
            </Button>
            <Button
              variant={view === 'list' ? 'secondary' : 'ghost'}
              size="icon"
              onClick={() => setView('list')}
            >
              <List className="h-4 w-4" />
            </Button>
            <Button size="sm" onClick={() => setShowUpload(true)} className="ml-2">
              <Plus className="h-4 w-4 mr-1" />
              Add paper
            </Button>
          </div>
        </div>
      </div>

      <ScrollArea className="flex-1 px-6 py-4">
        {filtered.length === 0 ? (
          <div className="flex items-center justify-center h-32 text-muted-foreground text-sm">
            {query ? 'No papers match your search.' : 'No ready papers yet.'}
          </div>
        ) : (
          <div
            className={
              view === 'grid'
                ? 'grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3'
                : 'space-y-2'
            }
          >
            {filtered.map((p) => (
              <PaperCard key={p.id} paper={p} onStatusChange={handleStatusChange} />
            ))}
          </div>
        )}
      </ScrollArea>
    </div>
  )
}
