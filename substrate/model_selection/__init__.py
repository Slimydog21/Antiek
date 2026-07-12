"""Model-selection pure substrates (asks #8/#9/#10 — the model decision tree).

Import-free pure-Python substrates that turn the bench's per-(task, model)
scores, the operator's per-model cost basis, the budget projection, and the
operator's constraints into a ranked, explained, advisory model recommendation.
Advisory only — the operator picks the model; this never dispatches or routes.
"""
