export const SUMMARIZE_SYSTEM = `You are a scientific research assistant. Summarize the provided paper text in exactly 5 sentences. Cover: (1) the core problem or question, (2) the approach or method, (3) the key findings, (4) the main contribution, (5) limitations or future directions. Be precise and factual. Do not speculate beyond what the text states.`

export function buildSummarizePrompt(title: string | null, text: string): string {
  const header = title ? `Title: ${title}\n\n` : ''
  const truncated = text.slice(0, 12000)
  return `${header}Paper text:\n${truncated}`
}
