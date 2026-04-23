import Anthropic from '@anthropic-ai/sdk'

export const anthropic = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY })

export const CLAUDE_MODEL = 'claude-sonnet-4-5'

export async function complete(systemPrompt: string, userContent: string): Promise<string> {
  const message = await anthropic.messages.create({
    model: CLAUDE_MODEL,
    max_tokens: 2048,
    system: systemPrompt,
    messages: [{ role: 'user', content: userContent }],
  })

  const block = message.content[0]
  if (block.type !== 'text') throw new Error('Unexpected response type from Claude')
  return block.text
}
