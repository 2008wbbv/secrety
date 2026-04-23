// Deterministic fake embedding — used when STUB_AI=true
export function stubEmbedding(seed = 0): number[] {
  return Array.from({ length: 1536 }, (_, i) => Math.sin((i + seed) * 0.01) * 0.1)
}

export const STUB_SUMMARY =
  'This paper presents a novel method for the research problem at hand. ' +
  'The authors combine several techniques to achieve state-of-the-art performance. ' +
  'Key results show significant improvement over baselines across multiple benchmarks. ' +
  'The main contribution is a unified framework that subsumes prior approaches. ' +
  'Limitations include computational cost and the need for large training datasets.'

export const STUB_ASSISTANT_RESPONSE =
  'Based on the papers in your library, the main finding is that [1] the proposed method outperforms baselines. ' +
  'This is further supported by [2] ablation studies showing each component contributes to the overall gain.'
