import OpenAI from 'openai'
import { stubEmbedding } from '@/lib/stubs'

const MODEL = 'text-embedding-3-small'
const BATCH_SIZE = 100

function isStub() {
  return process.env.STUB_AI === 'true'
}

export async function embedText(text: string): Promise<number[]> {
  if (isStub()) return stubEmbedding(text.length)

  const openai = new OpenAI({ apiKey: process.env.OPENAI_API_KEY })
  const response = await openai.embeddings.create({
    model: MODEL,
    input: text.replace(/\n/g, ' '),
  })
  return response.data[0].embedding
}

export async function embedBatch(texts: string[]): Promise<number[][]> {
  if (isStub()) return texts.map((t, i) => stubEmbedding(i + t.length))

  const openai = new OpenAI({ apiKey: process.env.OPENAI_API_KEY })
  const results: number[][] = []

  for (let i = 0; i < texts.length; i += BATCH_SIZE) {
    const batch = texts.slice(i, i + BATCH_SIZE).map((t) => t.replace(/\n/g, ' '))
    const response = await openai.embeddings.create({ model: MODEL, input: batch })
    results.push(...response.data.map((d) => d.embedding))
  }

  return results
}
