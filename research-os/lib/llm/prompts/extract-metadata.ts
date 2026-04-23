export const EXTRACT_METADATA_SYSTEM = `You are a metadata extraction assistant. Given the first page of a scientific paper, extract structured metadata as JSON. Return only valid JSON with these fields: title (string|null), authors (array of {name: string}), year (number|null), venue (string|null), abstract (string|null), doi (string|null), arxiv_id (string|null). If a field cannot be determined, use null.`

export const EXTRACT_METADATA_USER = (firstPageText: string) =>
  `Extract metadata from this paper text:\n\n${firstPageText.slice(0, 4000)}`
