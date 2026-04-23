import { createClient } from '@/lib/supabase/server'
import { Header } from '@/components/shell/header'
import { NoteList } from '@/components/notes/note-list'
import type { Note } from '@/types'

export default async function NotesPage() {
  const supabase = createClient()
  const { data: { user } } = await supabase.auth.getUser()

  const { data: notes } = await supabase
    .from('notes')
    .select('*')
    .eq('user_id', user!.id)
    .order('updated_at', { ascending: false })

  return (
    <div className="flex flex-col h-full">
      <Header title="Notes" />
      <NoteList initialNotes={(notes ?? []) as Note[]} userId={user!.id} />
    </div>
  )
}
