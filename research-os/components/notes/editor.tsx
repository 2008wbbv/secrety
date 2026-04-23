'use client'

import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'

interface NoteEditorProps {
  initialContent?: string
  autoFocus?: boolean
  onSave: (content: string) => void
  onCancel: () => void
}

export function NoteEditor({ initialContent = '', autoFocus, onSave, onCancel }: NoteEditorProps) {
  const [content, setContent] = useState(initialContent)

  const handleSave = () => {
    if (!content.trim()) return
    onSave(content.trim())
  }

  return (
    <div className="space-y-2">
      <Textarea
        value={content}
        onChange={(e) => setContent(e.target.value)}
        placeholder="Write a note..."
        className="min-h-[120px] text-sm resize-none"
        autoFocus={autoFocus}
        onKeyDown={(e) => {
          if (e.key === 'Escape') onCancel()
          if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') handleSave()
        }}
      />
      <div className="flex gap-2 justify-end">
        <Button variant="ghost" size="sm" onClick={onCancel}>Cancel</Button>
        <Button size="sm" onClick={handleSave} disabled={!content.trim()}>Save</Button>
      </div>
    </div>
  )
}
