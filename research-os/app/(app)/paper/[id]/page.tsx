import { notFound } from 'next/navigation'
import { createClient } from '@/lib/supabase/server'
import { PaperReader } from '@/components/reader/paper-reader'
import type { Paper, Note } from '@/types'

interface Props {
  params: { id: string }
}

export default async function PaperPage({ params }: Props) {
  const supabase = createClient()
  const { data: { user } } = await supabase.auth.getUser()

  const { data: paper } = await supabase
    .from('papers')
    .select('*')
    .eq('id', params.id)
    .eq('user_id', user!.id)
    .single()

  if (!paper) notFound()

  const { data: notes } = await supabase
    .from('notes')
    .select('*')
    .eq('paper_id', params.id)
    .eq('user_id', user!.id)
    .order('updated_at', { ascending: false })

  return (
    <PaperReader
      paper={paper as Paper}
      initialNotes={(notes ?? []) as Note[]}
      userId={user!.id}
    />
  )
}
