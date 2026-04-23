import { NextResponse } from 'next/server'
import { createClient } from '@/lib/supabase/server'
import { createAdminClient } from '@/lib/supabase/admin'
import { inngest } from '@/inngest/client'
import { fetchArxivMetadata } from '@/lib/metadata/arxiv'
import { fetchCrossrefMetadata } from '@/lib/metadata/crossref'

function detectIdentifier(input: string): { type: 'doi' | 'arxiv'; value: string } | null {
  const arxiv = input.match(/(?:arxiv[:\s/]*)(\d{4}\.\d{4,5}(?:v\d+)?)/i)
  if (arxiv) return { type: 'arxiv', value: arxiv[1] }

  const doi = input.match(/(?:doi[:\s/]*|https?:\/\/doi\.org\/)?(10\.\d{4,}\/\S+)/i)
  if (doi) return { type: 'doi', value: doi[1] }

  return null
}

export async function POST(request: Request): Promise<NextResponse> {
  const supabase = createClient()
  const admin = createAdminClient()

  const { data: { user } } = await supabase.auth.getUser()
  if (!user) return NextResponse.json({ error: 'Unauthorized', code: 401 }, { status: 401 })

  const contentType = request.headers.get('content-type') ?? ''

  if (contentType.includes('multipart/form-data')) {
    const form = await request.formData()
    const file = form.get('file') as File | null
    if (!file) return NextResponse.json({ error: 'No file', code: 400 }, { status: 400 })

    const { data: paper, error: insertError } = await admin
      .from('papers')
      .insert({ user_id: user.id, title: file.name.replace(/\.pdf$/i, ''), status: 'processing' })
      .select()
      .single()

    if (insertError) return NextResponse.json({ error: insertError.message, code: 500 }, { status: 500 })

    const storagePath = `${user.id}/${paper.id}.pdf`
    const { error: storageError } = await admin.storage
      .from('papers')
      .upload(storagePath, file, { contentType: 'application/pdf' })

    if (storageError) {
      await admin.from('papers').update({ status: 'failed', error_message: storageError.message }).eq('id', paper.id)
      return NextResponse.json({ error: storageError.message, code: 500 }, { status: 500 })
    }

    await admin.from('papers').update({ storage_path: storagePath }).eq('id', paper.id)
    await inngest.send({ name: 'paper/ingest', data: { paperId: paper.id, userId: user.id } })

    return NextResponse.json({ paperId: paper.id, status: 'processing' })
  }

  const body = await request.json() as { identifier?: string }
  const raw = body.identifier?.trim()
  if (!raw) return NextResponse.json({ error: 'identifier required', code: 400 }, { status: 400 })

  const detected = detectIdentifier(raw)
  if (!detected) return NextResponse.json({ error: 'Unrecognized DOI or arXiv ID', code: 400 }, { status: 400 })

  try {
    let meta: {
      title: string
      authors: { name: string }[]
      year: number | null
      venue?: string | null
      abstract?: string | null
      doi?: string | null
      arxiv_id?: string | null
      source_url?: string | null
    }

    if (detected.type === 'arxiv') {
      const m = await fetchArxivMetadata(detected.value)
      meta = { ...m, venue: null }
    } else {
      const m = await fetchCrossrefMetadata(detected.value)
      meta = { ...m, abstract: null, arxiv_id: null }
    }

    const { data: paper, error: insertError } = await admin
      .from('papers')
      .insert({
        user_id: user.id,
        title: meta.title,
        authors: meta.authors,
        year: meta.year,
        venue: meta.venue ?? null,
        abstract: meta.abstract ?? null,
        doi: meta.doi ?? null,
        arxiv_id: meta.arxiv_id ?? null,
        source_url: meta.source_url ?? null,
        status: 'processing',
      })
      .select()
      .single()

    if (insertError) return NextResponse.json({ error: insertError.message, code: 500 }, { status: 500 })

    await inngest.send({ name: 'paper/ingest', data: { paperId: paper.id, userId: user.id } })
    return NextResponse.json({ paperId: paper.id, status: 'processing' })
  } catch (err) {
    return NextResponse.json({ error: String(err), code: 500 }, { status: 500 })
  }
}
