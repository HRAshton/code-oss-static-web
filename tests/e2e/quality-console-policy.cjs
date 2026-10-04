const NORMALIZATION = 'strip-console-style-prefix';

function validateConsoleErrorPolicy(policy) {
  if (!policy || typeof policy !== 'object' || Array.isArray(policy)) {
    throw new Error('console error policy must be an object');
  }
  const expectedKeys = [
    'normalization',
    'requireAllToleratedObserved',
    'toleratedFingerprints',
  ];
  const actualKeys = Object.keys(policy).sort();
  if (JSON.stringify(actualKeys) !== JSON.stringify([...expectedKeys].sort())) {
    throw new Error('console error policy has unexpected or missing keys');
  }
  if (policy.normalization !== NORMALIZATION) {
    throw new Error('unsupported console error normalization: ' + policy.normalization);
  }
  if (typeof policy.requireAllToleratedObserved !== 'boolean') {
    throw new Error('requireAllToleratedObserved must be boolean');
  }
  if (
    !Array.isArray(policy.toleratedFingerprints) ||
    policy.toleratedFingerprints.length === 0
  ) {
    throw new Error('tolerated console fingerprints must be a non-empty array');
  }
  if (
    policy.toleratedFingerprints.some(
      item => typeof item !== 'string' || item.length === 0 || item.trim() !== item
    )
  ) {
    throw new Error('tolerated console fingerprints must be non-empty trimmed strings');
  }
  if (new Set(policy.toleratedFingerprints).size !== policy.toleratedFingerprints.length) {
    throw new Error('tolerated console fingerprints must be unique');
  }
}

function normalizeConsoleError(message) {
  return String(message).replace(
    /^%c\s+ERR\s+color:\s*#[0-9a-fA-F]+\s+/,
    'ERR '
  );
}

function evaluateConsoleErrors(occurrences, policy) {
  validateConsoleErrorPolicy(policy);
  const normalizedOccurrences = occurrences.map(normalizeConsoleError);
  const observed = [...new Set(normalizedOccurrences)].sort();
  const tolerated = [...policy.toleratedFingerprints].sort();
  const toleratedSet = new Set(tolerated);
  const observedSet = new Set(observed);
  const unexpected = observed.filter(item => !toleratedSet.has(item));
  const stale = tolerated.filter(item => !observedSet.has(item));
  return {
    normalizedOccurrences,
    observedFingerprints: observed,
    unexpectedFingerprints: unexpected,
    staleFingerprints: stale,
  };
}

module.exports = {
  normalizeConsoleError,
  validateConsoleErrorPolicy,
  evaluateConsoleErrors,
};
