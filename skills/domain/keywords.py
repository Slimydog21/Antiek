"""Domain classification — deterministic keyword matching.

Verbatim port of Researchmaxx ``knowledge_extraction.py`` (Sprint 6 day
2-3). One investigation can match multiple domains (the operator's
2026-05-14 WP-A4 fix specifically expanded ai-infrastructure-knowledge
so syntheses written in strategy/economics language match alongside
hardware-specific ones — see the inline comments inside
``DOMAIN_KEYWORDS["ai-infrastructure-knowledge"]``).

Matching is case-insensitive substring against ``question + thesis_summary
+ thesis_components[].claim``. A single keyword hit is sufficient
because the keyword lists are domain-specific by construction —
deliberately short, deliberately unambiguous (``"ew"`` and ``"dod"``
are excluded because they collide with common words; see the
defense-systems-knowledge inline note).
"""

from __future__ import annotations

from typing import Any, Dict, List


DOMAIN_KEYWORDS: Dict[str, List[str]] = {
    "quantum-computing-knowledge": [
        "quantum", "qubit", "error correction", "fault-tolerant", "fault-tolerance",
        "psiQuantum", "ion trap", "superconducting qubit", "neutral atom",
        "photonic", "topological qubit", "quantum advantage", "qpu",
        "shor", "surface code", "logical qubit", "decoherence",
        "ionq", "rigetti computing", "xanadu", "quera", "quantinuum",
    ],
    "semiconductor-knowledge": [
        "semiconductor", "chip", "fab", "foundry", "tsmc", "asml", "intel",
        "samsung foundry", "process node", "euv", "lithography", "packaging",
        "chiplets", "hbm", "dram", "nand", "memory", "interconnect",
        "cowos", "emib", "foveros", "high na", "backside power",
        "gate-all-around", "gaa", "ucie", "hybrid bonding",
        "applied materials", "lam research", "kla", "tokyo electron",
    ],
    "ai-infrastructure-knowledge": [
        "ai infrastructure", "gpu", "tpu", "inference", "training cluster",
        "llm", "large language model", "datacenter", "data center",
        "nvidia", "h100", "b200", "b100", "hopper", "blackwell",
        "mi300", "mi250", "amd instinct", "intel gaudi",
        "cloud compute", "model serving", "neural network accelerator",
        "memory bandwidth", "interconnect bandwidth", "nvlink",
        "transformer", "attention mechanism", "token",
        "openai", "anthropic", "google deepmind", "meta ai",
        "model training cost", "inference cost", "tokens per second",
        # 2026-05-14 expansion (WP-A4): higher-level AI/compute policy
        # terminology so syntheses written in strategy/economics language
        # match ai-infrastructure-knowledge alongside hardware-specific ones.
        # See compound-test-001 diagnosis: question was about open-source AI
        # closing the performance gap but only matched
        # semiconductor-knowledge because the original keyword list was
        # entirely hardware-flavored.
        "compute efficiency", "compute constraints", "compute deficit",
        "compute stock", "compute access", "compute budget",
        "compute allocation", "compute capability", "training compute",
        "frontier labs", "frontier lab", "frontier models", "frontier model",
        "frontier ai", "model performance gap",
        "algorithmic efficiency", "model distillation",
        "ai capability", "algorithm innovation",
        "open-source model", "open source model",
        "open-source ai", "open source ai",
    ],
    "defense-systems-knowledge": [
        # Substring matches against the whole thesis text. Avoid short
        # tokens like "ew" / "dod" — they match inside common words
        # ("new", "view", "knew", "doddering") and cause false positives.
        # The unabbreviated form below already covers the concept.
        "defense", "military", "weapon", "drone", "anduril", "palmer luckey",
        "autonomous system", "electronic warfare", "missile",
        "hypersonic", "supply chain security", "darpa", "pentagon",
        "department of defense", "navy", "air force", "army",
        "lockheed", "raytheon", "northrop", "boeing defense",
        "counter-drone", "c-uas", "loitering munition", "switchblade",
        "shield ai", "epirus", "helion", "castelion",
    ],
    "radar-knowledge": [
        # Core domain
        "passive radar", "passive bistatic radar", "passive coherent location",
        "multistatic radar", "phased array radar", "phased-array radar",
        "active electronically scanned array", "aesa",
        "illuminator of opportunity", "illuminators of opportunity",
        # Signal-processing terminology
        "matched filter", "ambiguity function", "range-doppler",
        "clutter cancellation", "direct path interference",
        "cross-ambiguity function", "caf", "eca", "nlms",
        "beamforming", "digital beamforming", "monopulse",
        "synthetic aperture", "sar", "doppler processing",
        # Illuminator-specific signals
        "dvb-t", "dvb-s", "fm radio illuminator", "gsm illuminator",
        "lte illuminator", "5g illuminator", "wifi radar",
        "starlink illuminator",
        # Applications
        "counter-uas", "counter-drone radar",
        "air surveillance", "maritime surveillance",
        "space surveillance", "space situational awareness",
        "murchison widefield array",
        # Named systems
        "passat", "aulos", "vera-ng", "silent sentry",
        # People (authors who anchor the literature)
        "cherniakov", "howland", "griffiths", "malanowski", "kuschel",
        "yazici",
    ],
    "marketing-knowledge": [
        # Practitioners / canon
        "bernays", "edward bernays", "ogilvy", "david ogilvy",
        "claude hopkins", "rosser reeves",
        # Discipline terms — broad enough to catch synthesis prose
        "marketing", "advertising", "advertisement", "public relations",
        "public relations counsel", "press agentry", "publicity",
        # Bernays-specific framework vocabulary
        "engineering of consent", "invisible government",
        "crystallizing public opinion", "propaganda",
        "third-party endorsement", "third party endorsement",
        "front organization", "opinion leader", "herd instinct",
        # Modern marketing/consumer-psych terms that downstream
        # investigations comparing Bernays to current practice will
        # surface
        "consumer behavior", "consumer psychology",
        "brand", "branding", "brand equity",
        "campaign", "campaigns",
        "influencer", "influencer marketing",
        "neuromarketing", "behavioral economics in marketing",
        "programmatic advertising",
    ],
}


def classify_domains(question: str, thesis: Any) -> List[str]:
    """Return knowledge skill names that match this investigation.

    Matches against ``question`` + ``thesis.thesis_summary`` +
    each ``thesis.thesis_components[].claim``. Case-insensitive
    substring. A single keyword hit is sufficient — keyword lists are
    domain-specific by construction.

    ``thesis`` may be the parsed dict OR something else (None, list)
    in which case only ``question`` is searched. The upstream's
    defensive ``isinstance(thesis, dict)`` checks are preserved here.
    """
    text = (question or "").lower()
    if isinstance(thesis, dict):
        text += " " + (thesis.get("thesis_summary") or "").lower()
        for comp in thesis.get("thesis_components") or []:
            if isinstance(comp, dict):
                text += " " + (comp.get("claim") or "").lower()

    matched: List[str] = []
    for skill_name, keywords in DOMAIN_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            matched.append(skill_name)
    return matched
