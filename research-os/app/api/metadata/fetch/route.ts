import { NextResponse } from 'next/server'
import { createClient } from '@/lib/supabase/server'
import { fetchArxivMetadata } from '@/lib/metadata/arxiv'
import { fetchCrossrefMetadata } from '@/lib/metadata/crossref'

export async function GET(request: Request): Promise<NextResponse> {
  const supabase = createClient()
  const { data: { user } } = await supabase.auth.getUser()
  if (!user) return NextResponse.json({ error: 'Unauthorized', code: 401 }, { status: 401 })

  const { searchParams } = new URL(request.url)
  const id = searchParams.get('id')?.trim()
  const type = searchParams.get('type') as 'doi' | 'arxiv' | null

  if (!id || !type) return NextResponse.json({ error: 'id and type required', code: 400 }, { status: 400 })

  try {
    const meta = type === 'arxiv'
      ? await fetchArxivMetadata(id)
      : await fetchCrossrefMetadata(id)
    return NextResponse.json({ meta })
  } catch (err) {
    return NextResponse.json({ error: String(err), code: 500 }, { status: 500 })
  }
}
