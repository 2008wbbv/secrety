import { createClient } from '@/lib/supabase/server'
import { Header } from '@/components/shell/header'
import { ChatPane } from '@/components/assistant/chat-pane'
import { ThreadList } from '@/components/assistant/thread-list'
import type { AssistantThread } from '@/types'

export default async function AssistantPage() {
  const supabase = createClient()
  const { data: { user } } = await supabase.auth.getUser()

  const { data: threads } = await supabase
    .from('assistant_threads')
    .select('*')
    .eq('user_id', user!.id)
    .order('updated_at', { ascending: false })
    .limit(20)

  return (
    <div className="flex flex-col h-full">
      <Header title="Assistant" />
      <div className="flex flex-1 overflow-hidden">
        <ThreadList threads={(threads ?? []) as AssistantThread[]} />
        <ChatPane userId={user!.id} />
      </div>
    </div>
  )
}
