'use client'

import { useState } from 'react'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { useToast } from '@/components/ui/use-toast'

interface DOIInputProps {
  onAdded: (paperId: string) => void
}

export function DOIInput({ onAdded }: DOIInputProps) {
  const [value, setValue] = useState('')
  const [loading, setLoading] = useState(false)
  const { toast } = useToast()

  const handleAdd = async () => {
    const trimmed = value.trim()
    if (!trimmed) return
    setLoading(true)
    try {
      const res = await fetch('/api/ingest', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ identifier: trimmed }),
      })
      const data = await res.json() as { paperId?: string; error?: string }
      if (!res.ok || data.error) throw new Error(data.error ?? 'Failed to add paper')
      toast({ title: 'Processing started' })
      setValue('')
      onAdded(data.paperId!)
    } catch (err) {
      toast({ title: 'Failed', description: String(err), variant: 'destructive' })
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex gap-2">
      <Input
        placeholder="Paste DOI or arXiv ID (e.g. 2303.08774)"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => { if (e.key === 'Enter') handleAdd() }}
        disabled={loading}
      />
      <Button onClick={handleAdd} disabled={loading || !value.trim()}>
        {loading ? 'Adding...' : 'Add'}
      </Button>
    </div>
  )
}
