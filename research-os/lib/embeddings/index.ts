import OpenAI from 'openai'

const openai = new OpenAI({ apiKey: process.env.OPENAI_API_KEY })

const MODEL = 'text-embedding-3-small'
const BATCH_SIZE = 100

export async function embedText(text: string): Promise<number[]> {
  const response = await openai.embeddings.create({
    model: MODEL,
    input: text.replace(/\n/g, ' '),
  })
  return response.data[0].embedding
}

export async function embedBatch(texts: string[]): Promise<number[][]> {
  const results: number[][] = []

  for (let i = 0; i < texts.length; i += BATCH_SIZE) {
    const batch = texts.slice(i, i + BATCH_SIZE).map((t) => t.replace(/\n/g, ' '))
    const response = await openai.embeddings.create({ model: MODEL, input: batch })
    results.push(...response.data.map((d) => d.embedding))
  }

  return results
}
