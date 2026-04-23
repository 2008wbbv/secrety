'use client'

import Link from 'next/link'
import { FileText, Clock } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { createClient } from '@/lib/supabase/client'
import type { Paper, ReadingStatus } from '@/types'

const STATUS_LABELS: Record<ReadingStatus, string> = {
  unread: 'Unread',
  queued: 'Queued',
  reading: 'Reading',
  read: 'Read',
}

interface PaperCardProps {
  paper: Paper
  onStatusChange: (id: string, status: ReadingStatus) => void
}

export function PaperCard({ paper, onStatusChange }: PaperCardProps) {
  const supabase = createClient()
  const authors = paper.authors.slice(0, 2).map((a) => a.name).join(', ')
  const hasMore = paper.authors.length > 2

  const handleStatusChange = async (value: string) => {
    const status = value as ReadingStatus
    onStatusChange(paper.id, status)
    await supabase.from('papers').update({ reading_status: status }).eq('id', paper.id)
  }

  return (
    <Card className="hover:shadow-md transition-shadow group">
      <CardContent className="p-4">
        <div className="flex gap-3">
          <div className="mt-0.5 shrink-0">
            <FileText className="h-5 w-5 text-muted-foreground" />
          </div>
          <div className="flex-1 min-w-0">
            <Link href={`/paper/${paper.id}`} className="block">
              <h3 className="font-medium text-sm leading-snug line-clamp-2 group-hover:text-primary transition-colors">
                {paper.title ?? 'Untitled'}
              </h3>
            </Link>
            <p className="text-xs text-muted-foreground mt-1 truncate">
              {authors}{hasMore ? ' et al.' : ''}{paper.year ? ` (${paper.year})` : ''}
            </p>
            {paper.venue && (
              <p className="text-xs text-muted-foreground truncate">{paper.venue}</p>
            )}
            <div className="flex items-center gap-2 mt-2">
              <Select value={paper.reading_status} onValueChange={handleStatusChange}>
                <SelectTrigger className="h-6 text-xs w-24 px-2">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {(Object.keys(STATUS_LABELS) as ReadingStatus[]).map((s) => (
                    <SelectItem key={s} value={s} className="text-xs">
                      {STATUS_LABELS[s]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {paper.page_count && (
                <span className="text-xs text-muted-foreground flex items-center gap-1">
                  <Clock className="h-3 w-3" />
                  {paper.page_count}p
                </span>
              )}
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
