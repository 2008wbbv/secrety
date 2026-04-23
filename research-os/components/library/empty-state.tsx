import { BookOpen } from 'lucide-react'
import { Button } from '@/components/ui/button'

interface EmptyStateProps {
  onUpload: () => void
}

export function EmptyState({ onUpload }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center h-full gap-4 text-center px-4">
      <div className="rounded-full bg-muted p-4">
        <BookOpen className="h-8 w-8 text-muted-foreground" />
      </div>
      <div>
        <h2 className="text-lg font-semibold">Your library is empty</h2>
        <p className="text-sm text-muted-foreground mt-1">
          Add papers by uploading a PDF or pasting a DOI or arXiv link.
        </p>
      </div>
      <Button onClick={onUpload}>Add your first paper</Button>
    </div>
  )
}
