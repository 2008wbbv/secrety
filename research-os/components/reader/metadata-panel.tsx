import { ExternalLink } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Separator } from '@/components/ui/separator'
import type { Paper } from '@/types'

interface MetadataPanelProps {
  paper: Paper
}

export function MetadataPanel({ paper }: MetadataPanelProps) {
  const authors = paper.authors.map((a) => a.name).join(', ')

  return (
    <ScrollArea className="h-full">
      <div className="p-4 space-y-4">
        <div>
          <h2 className="font-semibold text-sm leading-snug">{paper.title ?? 'Untitled'}</h2>
          {authors && <p className="text-xs text-muted-foreground mt-1">{authors}</p>}
          <div className="flex items-center gap-2 mt-2 flex-wrap">
            {paper.year && <Badge variant="outline">{paper.year}</Badge>}
            {paper.venue && <Badge variant="outline" className="truncate max-w-[12rem]">{paper.venue}</Badge>}
          </div>
        </div>

        {(paper.doi || paper.arxiv_id) && (
          <>
            <Separator />
            <div className="space-y-1">
              {paper.doi && (
                <a
                  href={`https://doi.org/${paper.doi}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1 text-xs text-primary hover:underline"
                >
                  <ExternalLink className="h-3 w-3" />
                  DOI: {paper.doi}
                </a>
              )}
              {paper.arxiv_id && (
                <a
                  href={`https://arxiv.org/abs/${paper.arxiv_id}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1 text-xs text-primary hover:underline"
                >
                  <ExternalLink className="h-3 w-3" />
                  arXiv: {paper.arxiv_id}
                </a>
              )}
            </div>
          </>
        )}

        {paper.abstract && (
          <>
            <Separator />
            <div>
              <h3 className="text-xs font-semibold uppercase text-muted-foreground mb-2">Abstract</h3>
              <p className="text-xs leading-relaxed">{paper.abstract}</p>
            </div>
          </>
        )}

        {paper.summary && (
          <>
            <Separator />
            <div>
              <h3 className="text-xs font-semibold uppercase text-muted-foreground mb-2">AI Summary</h3>
              <p className="text-xs leading-relaxed">{paper.summary}</p>
            </div>
          </>
        )}
      </div>
    </ScrollArea>
  )
}
