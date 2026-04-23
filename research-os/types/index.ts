export type PaperStatus = 'processing' | 'ready' | 'failed'
export type ReadingStatus = 'unread' | 'queued' | 'reading' | 'read'

export interface Author {
  name: string
  orcid?: string
}

export interface Paper {
  id: string
  user_id: string
  title: string | null
  authors: Author[]
  year: number | null
  venue: string | null
  abstract: string | null
  doi: string | null
  arxiv_id: string | null
  semantic_scholar_id: string | null
  source_url: string | null
  storage_path: string | null
  page_count: number | null
  status: PaperStatus
  reading_status: ReadingStatus
  summary: string | null
  error_message: string | null
  created_at: string
  updated_at: string
}

export interface Chunk {
  id: string
  paper_id: string
  user_id: string
  chunk_index: number
  content: string
  page_number: number | null
  char_start: number | null
  char_end: number | null
  token_count: number | null
  created_at: string
}

export interface Note {
  id: string
  user_id: string
  paper_id: string | null
  title: string | null
  content: string
  linked_chunk_ids: string[]
  created_at: string
  updated_at: string
}

export interface Citation {
  index: number
  chunk_id: string
  paper_id: string
  paper_title: string | null
  page_number: number | null
}

export interface AssistantThread {
  id: string
  user_id: string
  title: string | null
  created_at: string
  updated_at: string
}

export interface AssistantMessage {
  id: string
  thread_id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  citations: Citation[]
  created_at: string
}

export interface ChunkSearchResult {
  id: string
  paper_id: string
  content: string
  page_number: number | null
  similarity: number
}

export interface ChunkWithPaper extends ChunkSearchResult {
  paper: Pick<Paper, 'id' | 'title' | 'authors' | 'year'>
}

export interface Collection {
  id: string
  user_id: string
  name: string
  description: string | null
  created_at: string
}

export interface IngestPayload {
  paperId: string
  userId: string
}
