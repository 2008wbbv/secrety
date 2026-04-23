'use client'

import { useRef, useState } from 'react'
import { Upload, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useToast } from '@/components/ui/use-toast'

interface UploadAreaProps {
  onUploaded: (paperId: string) => void
  onClose: () => void
}

export function UploadArea({ onUploaded, onClose }: UploadAreaProps) {
  const [dragging, setDragging] = useState(false)
  const [uploading, setUploading] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const { toast } = useToast()

  const upload = async (file: File) => {
    if (!file.type.includes('pdf')) {
      toast({ title: 'PDF files only', variant: 'destructive' })
      return
    }
    setUploading(true)
    const form = new FormData()
    form.append('file', file)
    try {
      const res = await fetch('/api/ingest', { method: 'POST', body: form })
      const data = await res.json() as { paperId?: string; error?: string }
      if (!res.ok || data.error) throw new Error(data.error ?? 'Upload failed')
      toast({ title: 'Processing started', description: 'Your paper is being processed.' })
      onUploaded(data.paperId!)
    } catch (err) {
      toast({ title: 'Upload failed', description: String(err), variant: 'destructive' })
    } finally {
      setUploading(false)
    }
  }

  return (
    <div className="relative rounded-lg border-2 border-dashed border-muted-foreground/30 p-8">
      <button
        type="button"
        className="absolute top-2 right-2 text-muted-foreground hover:text-foreground"
        onClick={onClose}
      >
        <X className="h-4 w-4" />
      </button>
      <div
        className={`flex flex-col items-center gap-3 transition-colors ${dragging ? 'text-primary' : 'text-muted-foreground'}`}
        onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault()
          setDragging(false)
          const file = e.dataTransfer.files[0]
          if (file) upload(file)
        }}
      >
        <Upload className="h-8 w-8" />
        <p className="text-sm font-medium">Drop a PDF here, or click to browse</p>
        <Button
          variant="outline"
          size="sm"
          disabled={uploading}
          onClick={() => inputRef.current?.click()}
        >
          {uploading ? 'Uploading...' : 'Choose file'}
        </Button>
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,application/pdf"
          className="hidden"
          onChange={(e) => { const f = e.target.files?.[0]; if (f) upload(f) }}
        />
      </div>
    </div>
  )
}
