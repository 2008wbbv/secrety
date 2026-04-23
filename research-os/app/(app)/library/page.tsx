import { createClient } from '@/lib/supabase/server'
import { Header } from '@/components/shell/header'
import { LibraryClient } from '@/components/library/library-client'
import type { Paper } from '@/types'

export default async function LibraryPage() {
  const supabase = createClient()
  const { data: { user } } = await supabase.auth.getUser()

  const { data: papers } = await supabase
    .from('papers')
    .select('*')
    .eq('user_id', user!.id)
    .order('created_at', { ascending: false })

  return (
    <div className="flex flex-col h-full">
      <Header title="Library" />
      <LibraryClient initialPapers={(papers ?? []) as Paper[]} userId={user!.id} />
    </div>
  )
}
