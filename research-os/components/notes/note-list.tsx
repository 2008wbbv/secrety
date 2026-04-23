'use client'

import { useState } from 'react'
import { Plus, FileText } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { NoteEditor } from '@/components/notes/editor'
import { createClient } from '@/lib/supabase/client'
import { useToast } from '@/components/ui/use-toast'
import type { Note } from '@/types'

interface Props {
  initialNotes: Note[]
  userId: string
}

export function NoteList({ initialNotes, userId }: Props) {
  const [notes, setNotes] = useState<Note[]>(initialNotes)
  const [creating, setCreating] = useState(false)
  const [editing, setEditing] = useState<Note | null>(null)
  const supabase = createClient()
  const { toast } = useToast()

  const handleCreate = async (content: string) => {
    const { data, error } = await supabase
      .from('notes')
      .insert({ user_id: userId, content })
      .select()
      .single()
    if (error) { toast({ title: 'Failed', variant: 'destructive' }); return }
    setNotes((p) => [data as Note, ...p])
    setCreating(false)
  }

  const handleUpdate = async (note: Note, content: string) => {
    await supabase.from('notes').update({ content }).eq('id', note.id)
    setNotes((p) => p.map((n) => (n.id === note.id ? { ...n, content } : n)))
    setEditing(null)
  }

  const handleDelete = async (id: string) => {
    await supabase.from('notes').delete().eq('id', id)
    setNotes((p) => p.filter((n) => n.id !== id))
  }

  return (
    <div className="flex flex-col h-full">
      <div className="px-6 py-3 border-b flex items-center justify-between">
        <span className="text-sm text-muted-foreground">{notes.length} note{notes.length !== 1 ? 's' : ''}</span>
        <Button size="sm" onClick={() => setCreating(true)}>
          <Plus className="h-4 w-4 mr-1" />
          New note
        </Button>
      </div>

      <ScrollArea className="flex-1">
        <div className="p-6 space-y-4 max-w-2xl">
          {creating && (
            <NoteEditor autoFocus onSave={handleCreate} onCancel={() => setCreating(false)} />
          )}

          {notes.length === 0 && !creating ? (
            <div className="flex flex-col items-center justify-center py-20 gap-3 text-muted-foreground">
              <FileText className="h-10 w-10 opacity-30" />
              <p className="text-sm">No notes yet.</p>
            </div>
          ) : (
            notes.map((note) =>
              editing?.id === note.id ? (
                <NoteEditor
                  key={note.id}
                  initialContent={note.content}
                  autoFocus
                  onSave={(c) => handleUpdate(note, c)}
                  onCancel={() => setEditing(null)}
                />
              ) : (
                <div
                  key={note.id}
                  className="rounded-lg border p-4 cursor-pointer hover:bg-accent group transition-colors"
                  onClick={() => setEditing(note)}
                >
                  <p className="text-sm whitespace-pre-wrap leading-relaxed line-clamp-6">
                    {note.content || 'Empty note'}
                  </p>
                  <div className="flex items-center justify-between mt-3">
                    <span className="text-xs text-muted-foreground">
                      {new Date(note.updated_at).toLocaleDateString()}
                    </span>
                    <button
                      className="text-xs text-destructive opacity-0 group-hover:opacity-100 transition-opacity"
                      onClick={(e) => { e.stopPropagation(); handleDelete(note.id) }}
                    >
                      Delete
                    </button>
                  </div>
                </div>
              )
            )
          )}
        </div>
      </ScrollArea>
    </div>
  )
}
