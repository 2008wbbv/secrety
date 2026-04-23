import Anthropic from '@anthropic-ai/sdk'
import { STUB_SUMMARY, STUB_ASSISTANT_RESPONSE } from '@/lib/stubs'

export const CLAUDE_MODEL = 'claude-sonnet-4-5'

function isStub() {
  return process.env.STUB_AI === 'true'
}

// Used by summarize + metadata extraction prompts
export async function complete(systemPrompt: string, userContent: string): Promise<string> {
  if (isStub()) {
    if (systemPrompt.includes('summarize') || systemPrompt.includes('Summarize')) return STUB_SUMMARY
    if (systemPrompt.includes('assistant') || systemPrompt.includes('research')) return STUB_ASSISTANT_RESPONSE
    return `[stub] response to: ${userContent.slice(0, 80)}`
  }

  const anthropic = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY })
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

// Used directly by the assistant streaming route
export function getAnthropicClient(): Anthropic {
  if (isStub()) {
    throw new Error('Use createStubStream() in stub mode instead of getAnthropicClient()')
  }
  return new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY })
}

export async function* stubStream(text: string): AsyncGenerator<string> {
  const words = text.split(' ')
  for (const word of words) {
    yield word + ' '
    await new Promise((r) => setTimeout(r, 0))
  }
}
