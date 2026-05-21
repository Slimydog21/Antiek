/**
 * S3 demo panel — fake Notebook. Pure prose; the real Notebook
 * lands in S7 (TipTap block editor + substrate-refs).
 */
export function FakeNotebook() {
  return (
    <div className="p-5 max-w-prose font-serif text-[15px] leading-relaxed text-ink dark:text-bright">
      <h1 className="font-sans font-bold text-2xl mb-3">
        Neutral-atom gate errors — first pass
      </h1>
      <p>
        Three independent groups reported single-qubit gate error rates between
        8×10⁻⁴ and 1.5×10⁻³ at the 100-qubit scale during 2024–2025.
        The cross-comparison is not trivial because the gate-set choices
        affect the effective error rate.
      </p>
      <p className="mt-3">
        A circuit-depth normalisation narrows the gap by roughly half an
        order of magnitude but does not eliminate it. The remaining question
        worth chasing is whether the gap is genuine platform physics or an
        artefact of measurement methodology.
      </p>
      <h2 className="font-sans font-bold text-lg mt-5 mb-2">
        Open questions
      </h2>
      <ul className="list-disc list-inside space-y-1 text-[14.5px]">
        <li>Has anyone published a head-to-head benchmark with shared decomp?</li>
        <li>What's the effective gate fidelity after error-correction overhead?</li>
        <li>Where does the Vuletic preprint's number land after normalisation?</li>
      </ul>
    </div>
  );
}

export default FakeNotebook;
