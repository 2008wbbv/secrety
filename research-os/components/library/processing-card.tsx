import { Loader2, AlertCircle } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import type { Paper } from '@/types'

interface ProcessingCardProps {
  papers: Paper[]
}

export function ProcessingCard({ papers }: ProcessingCardProps) {
  if (papers.length === 0) return null

  return (
    <Card className="border-blue-200 bg-blue-50">
      <CardContent className="py-3 px-4">
        <div className="space-y-2">
          {papers.map((p) => (
            <div key={p.id} className="flex items-center gap-2 text-sm">
              {p.status === 'processing' ? (
                <Loader2 className="h-4 w-4 animate-spin text-blue-600 shrink-0" />
              ) : (
                <AlertCircle className="h-4 w-4 text-red-500 shrink-0" />
              )}
              <span className="font-medium truncate">{p.title ?? 'Processing...'}</span>
              {p.status === 'failed' && (
                <span className="text-red-500 text-xs shrink-0">Failed</span>
              )}
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}
