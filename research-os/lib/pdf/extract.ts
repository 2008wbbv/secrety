export interface ExtractedPDF {
  pages: string[]
  totalPages: number
  fullText: string
}

export async function extractPDFText(buffer: ArrayBuffer): Promise<ExtractedPDF> {
  const { extractText, getDocumentProxy } = await import('unpdf')
  const pdf = await getDocumentProxy(new Uint8Array(buffer))
  const { text: pages, totalPages } = await extractText(pdf, { mergePages: false })
  const fullText = (pages as string[]).join('\n\n')
  return { pages: pages as string[], totalPages, fullText }
}

export function isTextSufficient(text: string): boolean {
  return text.trim().length >= 500
}
