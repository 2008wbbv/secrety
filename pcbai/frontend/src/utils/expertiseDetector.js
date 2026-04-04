/**
 * Expertise detection utility.
 * Analyzes user messages to infer whether the user is a beginner, expert, or mixed.
 * Full implementation comes in Step 4.
 *
 * @typedef {'beginner' | 'expert' | 'mixed' | 'unknown'} ExpertiseLevel
 */

const EXPERT_SIGNALS = [
  // Technical terminology
  /\b(impedance|differential pair|net class|stackup|via stitch|thermal relief)\b/i,
  // Package designators
  /\b(0402|0603|0805|1206|SOT-23|SOT-223|QFN|QFP|DFN|TSSOP|SOIC)\b/i,
  // Standards
  /\b(IPC-2221|MIL-STD|JEDEC|IPC-\d+)\b/i,
  // IC part numbers (rough heuristic: letters + digits combo like TPS62840, STM32F4)
  /\b[A-Z]{2,}[0-9]{3,}[A-Z0-9]*\b/,
  // Precise electrical specs
  /\b\d+(\.\d+)?\s*(mA|uA|A|mV|uV|MHz|GHz|kHz|nH|uH|mH|pF|nF|uF)\b/i,
];

const BEGINNER_SIGNALS = [
  // Functional descriptions without technical terms
  /\b(something that|a thing that|make it|connect to my phone|turn on|light up)\b/i,
  // Consumer language
  /\b(bluetooth|wifi|wireless|phone|app|battery powered)\b/i,
  // Questions about basics
  /\b(what is|what are|how do I|can you explain)\b/i,
  // No mention of layers/packages (detected by absence — handled in scoring)
];

/**
 * Detect expertise level from an array of user message strings.
 * Returns a level and a confidence score (0–1).
 *
 * @param {string[]} messages
 * @returns {{ level: ExpertiseLevel, confidence: number }}
 */
export function detectExpertise(messages) {
  if (!messages || messages.length === 0) {
    return { level: 'unknown', confidence: 0 };
  }

  const combined = messages.join(' ');
  let expertScore = 0;
  let beginnerScore = 0;

  for (const pattern of EXPERT_SIGNALS) {
    if (pattern.test(combined)) expertScore++;
  }
  for (const pattern of BEGINNER_SIGNALS) {
    if (pattern.test(combined)) beginnerScore++;
  }

  const total = expertScore + beginnerScore;
  if (total === 0) return { level: 'unknown', confidence: 0 };

  const confidence = Math.min(total / 3, 1); // Saturates at 3 signals

  if (expertScore > 0 && beginnerScore > 0) {
    return { level: 'mixed', confidence };
  }
  if (expertScore > beginnerScore) {
    return { level: 'expert', confidence };
  }
  return { level: 'beginner', confidence };
}
