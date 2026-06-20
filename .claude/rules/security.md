# Security Rules

These rules apply to every agent (`frontend`, `backend`, `infrastructure`)
that writes application code, and to the `reviewer` agent when assessing a
PR. They encode standard OWASP-level practice. Treat any violation as a
blocker, not a style nit.

## 1. Secrets

- Never commit credentials, API keys, tokens, private keys, or connection
  strings to source. They belong in environment variables or a secrets
  manager, referenced via config, never hardcoded.
- Never log secrets, tokens, passwords, or full payment/PII data, even at
  debug level.
- If a `.env` file or similar is created for local config, it must be listed
  in `.gitignore` before anything is committed. Only an `.env.example` with
  placeholder values is committed.
- If you discover an already-committed secret while working, stop and flag it
  to the user immediately — do not just rotate or delete it silently.

## 2. Injection

- SQL: use parameterized queries / the ORM's query builder. Never
  string-concatenate or interpolate user input into a raw query.
- Shell/OS commands: never pass unsanitized user input to a shell, `exec`,
  or similar. Use argument arrays, not string interpolation, when a subprocess
  call is unavoidable.
- NoSQL/ORM queries: be aware operator injection is possible (e.g. Mongo
  `$where`/object injection) — validate and type input before it reaches the
  query layer.

## 3. Cross-site scripting (XSS) and output encoding

- Never render unsanitized user input as raw HTML. Use the framework's
  default escaping; avoid `dangerouslySetInnerHTML` / `innerHTML` /
  `v-html`-style raw injection unless the content is sanitized through a
  vetted library first.
- Set a sensible Content-Security-Policy where the project has a CSP layer;
  don't weaken an existing one to make a feature "just work."

## 4. Authentication and session handling

- Passwords are hashed with a modern adaptive algorithm (bcrypt, argon2,
  scrypt) — never stored in plaintext or hashed with a fast general-purpose
  hash (MD5, SHA-1, unsalted SHA-256).
- Session tokens / JWTs: set `HttpOnly`, `Secure`, and `SameSite` on cookies
  carrying session data. Don't store sensitive tokens in `localStorage` if an
  HttpOnly cookie is feasible instead.
- Enforce expiry and rotation on long-lived tokens; don't issue tokens with
  no expiry.
- Rate-limit or otherwise protect authentication endpoints (login, password
  reset, signup) against brute force.

## 5. Authorization

- Every endpoint or action that touches a specific user's data must check
  that the requesting identity is actually authorized for that resource —
  never trust a client-supplied user/account ID alone (insecure direct object
  reference).
- Default to deny: new routes/endpoints require explicit authorization
  checks, not opt-out.

## 6. Input validation and trust boundaries

- Validate and constrain all input at the point it enters the system
  (request body, query params, file uploads, webhook payloads) — type,
  length, format, and allowed values.
- Validate file uploads: restrict file type/size, never trust the
  client-supplied MIME type alone, and never execute or serve an uploaded
  file from a location that allows code execution.
- Treat all third-party/webhook payloads as untrusted input even if the
  source is "trusted" — verify signatures where the provider supports them.

## 7. Dependencies and supply chain

- Don't add a dependency with known unpatched CVEs or that is unmaintained
  when a maintained alternative exists.
- Pin dependency versions consistent with the repo's existing lockfile
  practice; don't introduce a second package manager.

## 8. Infrastructure (for the `infrastructure` agent)

- Containers run as a non-root user unless there's a documented reason not
  to.
- No secrets baked into Docker images or CI config files in plaintext; use
  build-time secrets or runtime injection.
- Default to least-privilege IAM/service permissions in any infra config —
  don't grant broad/admin scopes for convenience.
- Don't expose a service port or database publicly unless the story
  explicitly requires public access.

## 9. When in doubt

If a story seems to require violating any rule above to "work," stop and
surface it as a decision rather than silently complying or silently working
around it.
