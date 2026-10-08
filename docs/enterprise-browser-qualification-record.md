# Enterprise browser deployment qualification record

Copy this template into the company's **private** deployment, change-management, or promotion
system. Create a separate record for each exact deployment tuple and release artifact. This is a
manual evidence record, **not** a substitute for testing. Do not commit completed company records,
policy exports, authentication material, proxy credentials, or sensitive browser traces to this
public repository.

Follow the requirements in [Compatibility](../COMPATIBILITY.md). A Playwright engine pass alone
does not qualify a branded browser or managed company environment.

## Qualification identity

- Record/ticket ID and internal evidence location:
- Qualification date (YYYY-MM-DD):
- Operator and independent reviewer:
- **Disposition: NOT QUALIFIED** (change only after the reviewer confirms all required checks pass)
- Code OSS Static Web release tag:
- Immutable distribution identity (distribution tree SHA-256, release digest, or equivalent):
- Matching automated Playwright qualification run/evidence reference:
- Browser brand (**Chrome Enterprise**, **Edge Enterprise**, or **Firefox ESR**):
- Browser full version and release channel (not just the name of a channel):
- Version window at qualification date (Chrome current/previous Stable; Edge current Stable;
  Firefox current ESR):
- OS edition, version/build, and managed image identifier:
- Managed browser policy-set identifier/revision and applicable exceptions:
- Injected enterprise browser extensions that affect this application (or `none`):
- Company proxy/gateway/TLS-inspection path identifier (or `direct`):
- HTTPS static-hosting origin and exact base path:
- Normal persistent-storage mode and site-data retention policy:
- Company-supported locked application extensions and versions (or `none`):

## Manual tests against the real production path

Use the **exact release artifact**, branded browser, managed OS/profile/policies, proxy, and
production static host listed above. Start from a clean **non-private** browser profile, without
development flags. Store redacted screenshots, logs, or test-ticket links in the private evidence
system. Fill in an actual outcome (`PASS` / `FAIL` / `NOT RUN`) and an evidence reference for
**every** row; blank results or `NOT RUN` do not count as passing.

| ID | Required check | Outcome | Private evidence reference / failure notes |
| --- | --- | --- | --- |
| 1 | Load production base path; packaged workbench reaches ready state without fatal page errors | NOT RUN | |
| 2 | Edit text; keyboard command palette; Settings; workspace trust enabled | NOT RUN | |
| 3 | Reload and fully restart browser; verify expected browser-backed settings/state persists | NOT RUN | |
| 4 | Exercise activation and primary workflow of **each** supported locked extension (details below) | NOT RUN | |
| 5 | Managed policies and proxy permit CSP, modules, workers, storage, and required assets without fatal failures | NOT RUN | |
| 6 | Assets remain on correct origin/base path, with valid responses; no HTML fallback, blocking, substitution, or unqualified redirects | NOT RUN | |
| 7 | Record policy exceptions and deployment limitations (explicitly state `none` when absent) | NOT RUN | |

### Extension-by-extension evidence (check 4)

Record **every** company-supported locked extension ID, exact version, tested workflow, outcome,
and private evidence reference here. If there are no company-supported locked extensions, say
`none` and mark check 4 `PASS` with that rationale. A passing workbench does not automatically
qualify any extension.

| Extension ID and locked version | Primary workflow exercised | Outcome | Evidence reference / notes |
| --- | --- | --- | --- |
| | | NOT RUN | |

## Approval and scope

- Known limitations or approved policy exceptions (or `none`):
- Failures and follow-up change tickets (or `none`):
- Operator name, date, and completion acknowledgement:
- Independent reviewer name, date, and sign-off:
- Final verdict: **NOT QUALIFIED** / **QUALIFIED FOR THIS EXACT TUPLE ONLY**

The reviewer may mark `QUALIFIED FOR THIS EXACT TUPLE ONLY` **only** when the release artifact
and complete deployment tuple are identified; the matching Playwright engine evidence exists;
the browser version is inside the stated support window; **every** manual check passes (including
all listed extensions); limitations/exceptions are documented; and the evidence was independently
reviewed. An incomplete record, failure, changed tuple, or browser version outside that window
means **no branded enterprise support claim**. Requalify after material changes to the browser
version, OS image, policy set, proxy/network path, hosting, storage, release artifact, or supported
extension set.

Safari, mobile browsers, embedded browser hosts, and private browsing remain unsupported regardless
of this template.
