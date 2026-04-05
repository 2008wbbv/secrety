/**
 * Component disambiguation utility.
 * Resolves underspecified component descriptions to concrete specs.
 * Full implementation comes in Step 4 (integrated with Claude).
 *
 * @typedef {{ value: string, package: string, reasoning: string }} ResolvedComponent
 */

/**
 * Default package preferences by assembly method.
 * Used when no other context is available.
 */
const ASSEMBLY_METHOD_DEFAULTS = {
  hand: { resistor: '0805', capacitor: '0805', inductor: '1210' },
  reflow: { resistor: '0603', capacitor: '0603', inductor: '0805' },
  production: { resistor: '0402', capacitor: '0402', inductor: '0603' },
};

/**
 * Attempt to resolve a component description to a concrete spec using available context.
 *
 * @param {object} params
 * @param {string} params.description - Raw component description, e.g. "220 ohm resistor"
 * @param {object} params.context - Design context (assemblyMethod, powerDissipation, etc.)
 * @param {'beginner'|'expert'|'mixed'|'unknown'} params.expertiseLevel
 * @returns {{ resolved: boolean, component: ResolvedComponent | null, clarifyQuestion: string | null }}
 */
export function resolveComponent({ description, context = {}, expertiseLevel = 'unknown' }) {
  // TODO (Step 4): Replace with full resolution logic driven by Claude analysis

  const lower = description.toLowerCase();
  const isResistor = /resistor|ohm|Ω/.test(lower);
  const isCapacitor = /cap(acitor)?|farad/.test(lower);
  const isInductor = /inductor|henry/.test(lower);

  const type = isResistor ? 'resistor' : isCapacitor ? 'capacitor' : isInductor ? 'inductor' : null;

  if (!type) {
    return { resolved: false, component: null, clarifyQuestion: null };
  }

  // If assembly method is known, pick the appropriate default package
  const assemblyMethod = context.assemblyMethod ?? null;
  if (assemblyMethod && ASSEMBLY_METHOD_DEFAULTS[assemblyMethod]) {
    const pkg = ASSEMBLY_METHOD_DEFAULTS[assemblyMethod][type];
    return {
      resolved: true,
      component: {
        value: description,
        package: pkg,
        reasoning: `Selected ${pkg} based on ${assemblyMethod} assembly method.`,
      },
      clarifyQuestion: null,
    };
  }

  // No context — ask a targeted question based on expertise level
  const question =
    expertiseLevel === 'expert'
      ? `Package for ${description}? (0402/0603/0805/through-hole)`
      : `What size ${type} do you want? 0805 is easiest to hand solder and I'd recommend it for a first build. 0603 is standard. 0402 is very small and hard to hand solder.`;

  return { resolved: false, component: null, clarifyQuestion: question };
}
