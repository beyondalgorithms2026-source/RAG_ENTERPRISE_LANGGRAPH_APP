# Evaluation candidate cases

This file is a quarantine ledger, not an active evaluation set. A listed case has no
effect on CI or a baseline until it is independently source-reviewed and promoted in an
explicit pull request.

## Operations Manual v3.2 curation

The supplied 90-case draft contributed 65 cases to schema 1.1. The following 25 were
retained outside the blocking suite to reduce duplication, ambiguity, or category
imbalance.

| Draft ID | Disposition reason |
|---|---|
| OM-001 | Duplicates the manual identity/version metadata exercised by OM-002 and OM-003. |
| OM-005 | Broad scope-summary wording overlaps the source-guide/public-demo narrative. |
| OM-009 | Duplicates effective-date and applicability coverage. |
| OM-010 | Duplicates amendment-history lookup without adding a new failure boundary. |
| OM-014 | Near-duplicate of the adjacent financial-delegation table cases. |
| OM-020 | Redundant threshold lookup already covered across OM-015–019 and OM-021–022. |
| OM-024 | Conditional branch substantially overlaps OM-023 and OM-025. |
| OM-028 | Conditional branch substantially overlaps OM-027 and OM-029. |
| OM-037 | Cross-reference coverage duplicated by OM-033–036 and OM-038–040. |
| OM-043 | Definition is adequately covered by the surrounding definition cases. |
| OM-047 | Definition wording was ambiguous without additional scope context. |
| OM-048 | Definition wording was ambiguous without additional scope context. |
| OM-049 | Duplicates the selected numerical/table coverage. |
| OM-052 | Redundant numerical threshold case. |
| OM-062 | Negation wording overlapped OM-061 and OM-064. |
| OM-063 | Negation wording overlapped OM-064–066. |
| OM-073 | Procedure coverage duplicated by OM-067–072. |
| OM-074 | Procedure coverage duplicated by OM-067–072. |
| OM-076 | Safety prompt did not add a distinct refusal or boundary mechanism. |
| OM-078 | Safety prompt overlapped the selected boundary cases. |
| OM-079 | Safety prompt overlapped the selected strict-refusal cases. |
| OM-086 | Category balance favored the selected definition/conditional cases. |
| OM-087 | Category balance favored the selected cross-reference case. |
| OM-088 | Cross-document wording risked testing unavailable material rather than the manual. |
| OM-090 | Broad synthesis case was less deterministic than the selected fact-level cases. |

Reconsideration requires a documented production failure or material corpus change, a
source citation, explicit expected facts and aliases, and evidence that the case adds
coverage rather than merely increasing the count.
