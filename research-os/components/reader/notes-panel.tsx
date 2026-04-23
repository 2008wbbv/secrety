'use client'

import { useState } from 'react'
import { Plus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { NoteEditor } from '@/components/notes/editor'
import { createClient } from '@/lib/supabase/client'
import { useToast } from '@/components/ui/use-toast'
import type { Note } from '@/types'

interface NotesPanelProps {
  paperId: string
  userId: string
  initialNotes: Note[]
}

export function NotesPanel({ paperId, userId, initialNotes }: NotesPanelProps) {
  const [notes, setNotes] = useState<Note[]>(initialNotes)
  const [editing, setEditing] = useState<Note | null>(null)
  const [creating, setCreating] = useState(false)
  const supabase = createClient()
  const { toast } = useToast()

  const handleCreate = async (content: string) => {
    const { data, error } = await supabase
      .from('notes')
      .insert({ user_id: userId, paper_id: paperId, content })
      .select()
      .single()
    if (error) { toast({ title: 'Failed to save note', variant: 'destructive' }); return }
    setNotes((prev) => [data as Note, ...prev])
    setCreating(false)
  }

  const handleUpdate = async (note: Note, content: string) => {
    const { error } = await supabase.from('notes').update({ content }).eq('id', note.id)
    if (error) { toast({ title: 'Failed to update note', variant: 'destructive' }); return }
    setNotes((prev) => prev.map((n) => (n.id === note.id ? { ...n, content } : n)))
    setEditing(null)
  }

  const handleDelete = async (noteId: string) => {
    await supabase.from('notes').delete().eq('id', noteId)
    setNotes((prev) => prev.filter((n) => n.id !== noteId))
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-4 py-2 border-b">
        <span className="text-sm font-medium">Notes</span>
        <Button size="sm" variant="ghost" onClick={() => setCreating(true)}>
          <Plus className="h-4 w-4" />
        </Button>
      </div>
      <ScrollArea className="flex-1">
        <div className="p-3 space-y-3">
          {creating && (
            <NoteEditor
              autoFocus
              onSave={handleCreate}
              onCancel={() => setCreating(false)}
            />
          )}
          {notes.map((note) =>
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
                className="rounded border p-3 text-xs cursor-pointer hover:bg-accent group"
                onClick={() => setEditing(note)}
              >
                <p className="whitespace-pre-wrap leading-relaxed line-clamp-4">{note.content || 'Empty note'}</p>
                <button
                  className="text-destructive text-xs mt-2 opacity-0 group-hover:opacity-100"
                  onClick={(e) => { e.stopPropagation(); handleDelete(note.id) }}
                >
                  Delete
                </button>
              </div>
            )
          )}
          {notes.length === 0 && !creating && (
            <p className="text-xs text-muted-foreground text-center py-4">No notes yet. Click + to add one.</p>
          )}
        </div>
      </ScrollArea>
    </div>
  )
}
