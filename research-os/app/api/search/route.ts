import { NextResponse } from 'next/server'
import { createClient } from '@/lib/supabase/server'
import { searchChunks } from '@/lib/rag/search'

export async function POST(request: Request): Promise<NextResponse> {
  const supabase = createClient()
  const { data: { user } } = await supabase.auth.getUser()
  if (!user) return NextResponse.json({ error: 'Unauthorized', code: 401 }, { status: 401 })

  const body = await request.json() as { query?: string; limit?: number }
  const query = body.query?.trim()
  if (!query) return NextResponse.json({ error: 'query required', code: 400 }, { status: 400 })

  try {
    const results = await searchChunks(query, user.id, body.limit ?? 8)
    return NextResponse.json({ results })
  } catch (err) {
    return NextResponse.json({ error: String(err), code: 500 }, { status: 500 })
  }
}
