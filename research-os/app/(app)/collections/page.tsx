import { createClient } from '@/lib/supabase/server'
import { Header } from '@/components/shell/header'
import { FolderOpen } from 'lucide-react'
import type { Collection } from '@/types'

export default async function CollectionsPage() {
  const supabase = createClient()
  const { data: { user } } = await supabase.auth.getUser()

  const { data: collections } = await supabase
    .from('collections')
    .select('*')
    .eq('user_id', user!.id)
    .order('created_at', { ascending: false })

  const items = (collections ?? []) as Collection[]

  return (
    <div className="flex flex-col h-full">
      <Header title="Collections" />
      <div className="flex-1 overflow-auto p-6">
        {items.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full gap-3 text-muted-foreground">
            <FolderOpen className="h-12 w-12 opacity-30" />
            <p className="text-sm">No collections yet. Create one to organize your papers.</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {items.map((c) => (
              <div key={c.id} className="rounded-lg border p-4 hover:bg-accent transition-colors cursor-pointer">
                <div className="flex items-center gap-2 mb-1">
                  <FolderOpen className="h-4 w-4 text-muted-foreground" />
                  <span className="font-medium text-sm">{c.name}</span>
                </div>
                {c.description && <p className="text-xs text-muted-foreground">{c.description}</p>}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
