'use client'

import { useSearchParams, useRouter } from 'next/navigation'
import { MessageCircle } from 'lucide-react'
import { ScrollArea } from '@/components/ui/scroll-area'
import { cn } from '@/lib/utils'
import type { AssistantThread } from '@/types'

interface Props {
  threads: AssistantThread[]
}

export function ThreadList({ threads }: Props) {
  const searchParams = useSearchParams()
  const router = useRouter()
  const activeId = searchParams.get('thread')

  if (threads.length === 0) return null

  return (
    <div className="w-56 border-r flex flex-col">
      <div className="px-4 py-3 border-b">
        <span className="text-xs font-semibold uppercase text-muted-foreground">Threads</span>
      </div>
      <ScrollArea className="flex-1">
        <div className="p-2 space-y-1">
          {threads.map((t) => (
            <button
              key={t.id}
              onClick={() => router.push(`/assistant?thread=${t.id}`)}
              className={cn(
                'w-full text-left rounded-md px-3 py-2 text-sm transition-colors flex items-center gap-2',
                activeId === t.id
                  ? 'bg-accent text-accent-foreground'
                  : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
              )}
            >
              <MessageCircle className="h-3.5 w-3.5 shrink-0" />
              <span className="truncate">{t.title ?? 'New thread'}</span>
            </button>
          ))}
        </div>
      </ScrollArea>
    </div>
  )
}
