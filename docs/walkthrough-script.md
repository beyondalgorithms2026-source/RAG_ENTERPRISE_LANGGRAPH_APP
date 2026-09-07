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
7. Confirm the app shows four preset buttons. Start recording with the app tab selected.

## Timed narration and actions

### 0:00–0:25 — Set the boundary

**Say:**

> This is a self-built governed RAG portfolio demo using 27 synthetic Northwind Logistics
> documents. It is public on Render Free, but it is not a production or client deployment
> and contains no real company data. The agent has no direct database access: it calls a
> separate MCP integration layer, which calls the data backend where document access is
> enforced.

**Show:** The dashboard and its four preset buttons.

### 0:25–1:05 — Supported answer and source verification

**Action:** Click **1 · Answerable**.

**While it runs, say:**

> The first example asks a question the corpus can answer. The workflow retrieves evidence,
> checks whether the answer shape and citations are supported, and records the tool and
> decision timeline.

**After the result appears, say:**

> It returns 26 days, marks the result verified, and shows the exact source passage beside
> the answer. The citation is not just a label.

**Action:** Click **Open full source**. Briefly show the Annual Leave Policy and the
entitlement passage, then return to the app tab.

**Say:**

> A reader can open the complete synthetic source and check that the quoted passage was not
> removed from contradicting context.

### 1:05–1:40 — Refusal when evidence is absent

**Action:** Click **2 · Cannot answer**.

**Say while it runs:**

> This asks for company revenue, which is deliberately absent from the corpus. The desired
> behaviour is a refusal, not a plausible guess.

**After the result appears, say:**

> The result is not found, with no grounded answer and no citations. This visible refusal is
> one of the central controls in the demo.

### 1:40–2:15 — Human-review routing

**Action:** Click **3 · Human review**.

**Say while it runs:**

> This compliance question has supporting evidence, but the workflow treats policy answers
> as high risk when approval is requested.

**After the result appears, say:**

> The evidence check passes, but the answer is withheld as pending approval. Public visitors
> can see that it was routed for review, but they cannot approve, reject, or reveal it.

### 2:15–2:45 — Restricted-data attack

**Action:** Click **4 · Red-team**.

**Say while it runs:**

> The final prompt explicitly asks the system to ignore access controls and reveal restricted
> salary bands. The agent cannot widen its own access because retrieval permissions are
> enforced in the separate backend.

**After the result appears, say:**

> No grounded answer or restricted citation is returned. The prompt does not override the
> data-layer boundary.

### 2:45–3:05 — Close with measured scope

**Action:** Switch briefly to the public evaluation page.

**Say:**

> The public evaluation publishes the test questions, outcomes, limitations, and generated
> synthetic corpus so the evidence can be inspected. Its measured scope is 25 questions on
> 27 synthetic documents. This demonstrates governance behaviour; it is not a general
> accuracy, production-scale, or client-results claim.

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
