# Three-minute public demo walkthrough

This is an owner-recorded browser walkthrough of the synthetic public portfolio demo.
It does not show a client environment, real users, a real workload, source code, secrets,
the Render dashboard, or local infrastructure.

## Before recording

1. Use a quiet room and the Mac's built-in microphone (a headset is optional).
2. Open Loom's desktop recorder or browser recorder and sign in.
3. Choose **Window** and select only a clean browser window. Camera is optional.
4. Close notifications and private tabs. Do not open VS Code, Terminal, Render, `.env`
   files, password managers, billing pages, or API-key screens.
5. Open these two public tabs:
   - `https://rag-enterprise-governance-demo.onrender.com/app`
   - `https://beyondalgorithms2026-source.github.io/RAG_ENTERPRISE_LANGGRAPH_APP/evaluation/`
6. Wake the services before recording: load the app and, in another tab, open
   `https://rag-enterprise-starter-demo.onrender.com/health`. Wait until both load, then
   return to the app. Render Free can otherwise spend about a minute waking up.
7. Confirm the Ask page shows **Northline Analytics** as the selected company and four
   starter cards (Grounded, Refusal, Withheld, Denied). If it shows Northwind, pick
   Northline in the company switch. Start recording with the app tab selected.

## Timed narration and actions

### 0:00–0:25 — Set the boundary

**Say:**

> This is a self-built governed RAG portfolio demo over two fictional companies: Northline
> Analytics, with US and EU policies, and Northwind Logistics, the original demo. All data is
> synthetic. It runs on Render Free and is not a production or client deployment. The agent has
> no direct database access: it calls a separate MCP integration layer, which calls the data
> backend where document access is enforced. Each answer uses only the company you pick.

**Show:** The app bar, the company switch set to Northline, and the four starter cards.

### 0:25–1:05 — Supported answer and source verification

**Action:** Click the **Grounded** card ("What is the London hotel cap?").

**While it runs, say:**

> The first question is one the policies answer. The workflow retrieves evidence, checks that
> the answer and its citations are supported, and records each step.

**After the result appears, say:**

> It returns £240 a night, marked verified, with the expense policy and its rates appendix
> cited. The citation is not just a label.

**Action:** Click the first citation to open the source, briefly show the Hotel caps section,
then return to the app tab.

**Say:**

> Anyone can open the full synthetic source and check the passage in context.

### 1:05–1:30 — Refusal when evidence is absent

**Action:** Click the **Refusal** card ("What is the India PF contribution rate?").

**Say while it runs:**

> Northline has no India operations, so this fact is deliberately absent. The right behaviour
> is a refusal, not a plausible guess.

**After the result appears, say:**

> Not found, with no answer and no citations. A visible refusal is one of the central controls.

### 1:30–1:55 — Human-review routing

**Action:** Click the **Withheld** card ("Enhanced maternity pay in the UK?").

**Say while it runs:**

> This question has supporting evidence, but pay and leave answers are treated as high risk
> when approval is required.

**After the result appears, say:**

> The evidence check passes, but the answer is withheld pending approval. Public visitors can
> see that it was routed for review, but they cannot approve it or reveal it.

### 1:55–2:25 — Restricted document

**Action:** Click the **Denied** card ("First steps in a Sev1 outage?").

**Say while it runs:**

> The answer is in Northline's incident procedure, which is a restricted document. The public
> visitor's grant cannot retrieve it, and the agent cannot widen its own access, because
> permissions are enforced inside the backend's SQL.

**After the result appears, say:**

> The workflow tries several recovery steps and still returns not found, with no citations.
> The restricted text never reaches the agent.

### 2:25–2:50 — Show how it is checked

**Action:** Click **How it works** in the app bar, scroll briefly, then open **Quality**.

**Say:**

> Every claim on this page links to its proof. Quality shows the recorded evidence per
> company. Northline's 20-question demo set scored 15 out of 20, misses included. Northwind's
> approved v1 baseline is 25 out of 25. The 90-question v2 suite is calibration-only until
> approved.

### 2:50–3:05 — Close with measured scope

**Say:**

> This demonstrates governance behaviour on synthetic data: cited answers or an honest
> refusal, human review, and enforced access. It is not a general accuracy, production-scale,
> or client-results claim.

**Action:** Stop the recording.

## After recording

1. Let Loom finish uploading.
2. Play the video once. Confirm your voice is clear, no notification or secret appeared,
   and all four final states were visible.
3. Set access to **Anyone with the link can view** (wording may vary in Loom).
4. Open the link in a private/incognito browser window to confirm it works without login.
5. Send only the public Loom URL to the implementation thread. The implementation thread
   will add it to the README, run final checks, update the build log, commit and push.

If any scenario returns an HTTP or tool error, stop rather than narrating it as success.
Wake both services again, wait one minute and make a fresh recording.
