# R15 MCP authorization handoff, 2026-09-24

This candidate closes the local stdio disclosure paths in `search_public`,
`resources/read`, and `cite_source`. Private note reads require the exact
process-bound owner and a private note block. Public search requires a matching
query, an explicit public class, a collective owner or published contribution,
an active publisher opt-in where applicable, and no book takedown. Citation
metadata uses the same public test or the exact private owner.
Before public search serializes a matching chunk, it also runs the canonical
candidate-body serve guard. That guard re-derives arXiv rights from the stored
`license_uri` and requires a usable linkback for a body. A conflicting stored
rights tier or missing linkback excludes the body and its title from the search
result. Citation remains bibliographic and carries no body.

Book resource reads now refuse every request. The MCP graph has no authoritative
ISBN-to-edition/asset mapping and no current owner entitlement record to join at
read time. `record_attribution` also refuses every request because the caller's
investigation and dwell claims have no authenticated record to join. Reenable
either method only after those authorities exist and the subprocess tests cover
matched, wrong-owner, wrong-edition, expired, revoked, and forged claims.

`ANTIEK_MEMORY_OWNER` binds the stdio process but remains an environment value
chosen at launch. This patch does not prove that a deployed SSH principal is
mapped to that owner. Keep the multi-account release gate open until the
transport enforces that mapping and two signed accounts pass on the serving
revision. The local subprocess tests are candidate evidence, not production
proof.
