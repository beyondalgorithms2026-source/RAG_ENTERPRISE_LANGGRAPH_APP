# Public demo release checklist

Use this after the backend integration owner confirms that the deployed STARTER
service permits the public app origin and exposes public-grant corpus previews.

## Before deployment

- [ ] Public-demo branch changes only UI, deployment, smoke-check, and portfolio files.
- [ ] Quality-evidence branch changes are separate; the approved v1 baseline and its
      `docs/evaluation/status.json` are unchanged.
- [ ] APP test suite, JavaScript syntax check, Ruff check, and the deterministic red-team
      suite pass.
- [ ] Render app service uses the paid `starter` plan. The paired STARTER service is also
      upgraded from Free by its owner.

## Hosted verification

- [ ] `https://rag-enterprise-governance-demo.onrender.com/healthz` returns `status: ok`.
- [ ] `https://rag-enterprise-starter-demo.onrender.com/health` returns healthy status.
- [ ] An incognito browser opens `/app` with no login or console error.
- [ ] Desktop and 375px mobile layouts retain visible navigation, keyboard focus, labels,
      and a usable question input.
- [ ] Run all four public examples once: annual leave, gift cap, facilitation-payment
      exception, and withheld revenue.
- [ ] Confirm each supported answer has citations; open a source link, Documents, and the
      associated Audit record.
- [ ] Confirm the revenue request refuses without showing restricted content or provenance.
- [ ] Temporarily verify an unavailable-backend response says that no answer was fabricated.
- [ ] Quality shows the approved v1 evidence. Candidate v2 appears only when its public-safe
      provisional artifact exists.

## Screenshot and recording checklist

1. Open the public URL and state the five controls: citations, refusal, SQL access control,
   audit trail, and synthetic-corpus boundary.
2. Run the gift-cap example; show the answer, one citation, Documents, and Audit.
3. Run the revenue example; show the explicit withheld result and absence of restricted data.
4. Open Quality; distinguish approved 25-case v1 evidence from provisional 90-case work.
5. Capture 1440px desktop and 375px mobile screenshots after a clean browser reload.

Do not re-record or retune the UI after this list passes unless a functional defect, a
claim-safety problem, or a deployment failure is found.
