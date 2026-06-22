# Security Invariants

These 8 rules must NEVER be violated. They are enforced at the API layer and
must be preserved when modifying `ui/backend/auth.py`, `ui/backend/app.py`,
`ui/backend/runs.py`, or any endpoint that touches auth or user data.

---

## 1. SECRET_KEY must come from the environment

```python
SECRET_KEY = os.environ["SECRET_KEY"]   # raises KeyError → server refuses to start
# NEVER: SECRET_KEY = "hardcoded-value"
```

Generate with: `openssl rand -hex 32`

---

## 2. bcrypt cost ≥ 12

```python
pwd_context = CryptContext(schemes=["bcrypt"], bcrypt__rounds=12)
```

- Passwords are bcrypt-hashed at cost=12, never stored in plaintext.
- Passwords must never appear in logs, error messages, or API responses.

---

## 3. JWT cookies: httpOnly + secure + samesite=strict

```python
response.set_cookie(
    key="access_token",
    value=token,
    httponly=True,
    secure=True,
    samesite="strict",
    max_age=86400,
)
```

Never store JWTs in `localStorage` or return them in a JSON body.

---

## 4. Constant-time error messages for auth failures

```python
# CORRECT — same message for wrong user or wrong password
raise HTTPException(status_code=401, detail="Invalid credentials")

# NEVER — reveals whether the username exists
raise HTTPException(status_code=401, detail="User not found")
raise HTTPException(status_code=401, detail="Wrong password")
```

---

## 5. API keys stripped before DB writes

```python
# runs.py — strip before create_run()
safe_config = {k: v for k, v in model_config.items() if k != "api_key"}
run_id = db.create_run(user.user_id, request.feature_request, safe_config)
```

`api_key` from `StartRunRequest.model_config` must never be written to the DB.

---

## 6. WebSocket run ownership verification

```python
# BEFORE websocket.accept()
run = db.get_run(run_id, user.user_id)   # includes user_id filter
if not run:
    await websocket.close(code=4004)
    return
await websocket.accept()
```

Never accept a WebSocket for a run that doesn't belong to the authenticated user.

---

## 7. Rate limiting on real client IP

```python
# Keyed on client IP from X-Real-IP / X-Forwarded-For, not proxy IP
# 5 login attempts per 15 minutes
```

CORS `allow_origins` comes from `ALLOWED_ORIGINS` env var — never `"*"` with credentials.

---

## 8. CORS never `*` with credentials

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,   # from env var, e.g. ["http://localhost:5173"]
    allow_credentials=True,
    # NEVER: allow_origins=["*"] with allow_credentials=True
)
```

---

## OWASP Top 10 checklist (for security reviewers)

- **A01 Broken Access Control** — verify ownership before data access; no IDOR
- **A02 Cryptographic Failures** — bcrypt cost≥12; TLS everywhere; no MD5/SHA1 for secrets
- **A03 Injection** — parameterized SQL only; validate all inputs (see `coding-standards.md`)
- **A04 Insecure Design** — no sensitive data in URLs or logs; no self-registration bypass
- **A05 Security Misconfiguration** — no hardcoded secrets; CORS never `*` with credentials
- **A06 Vulnerable Components** — flag outdated dependencies or known CVEs
- **A07 Auth Failures** — httpOnly+secure+samesite cookies; constant-time token comparison
- **A08 Software/Data Integrity** — validate external content; no unsafe deserialization
- **A09 Logging Failures** — log security events (login, access denied); no PII in logs
- **A10 SSRF** — validate/allowlist URLs before any server-side HTTP fetch
