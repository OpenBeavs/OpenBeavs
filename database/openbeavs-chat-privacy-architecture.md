# **OpenBeavs — Chat Privacy & Authentication Architecture**

**Project context:** OpenBeavs is a forked Open WebUI frontend supporting Google’s A2A protocol, intended to be hosted across Oregon State University domain websites. Each site exposes a floating action button (FAB) that connects users to a centralized Agent Registry, routing them to specialized agents based on their task or question.

**Confirmed infrastructure decisions:** \- Identity: OAuth2 / OIDC (OSU SSO) \- Hosting: GCP or Azure (cloud-hosted) \- Users: Mix of students, staff/faculty, and public guests \- Cross-domain history: Isolated by default, opt-in sharing (see §5)

---

## **Table of Contents**

1. [Encryption Key Strategy](#bookmark=id.i07wvyjvoa5t)

2. [Session Authentication Timing](#bookmark=id.nnuzkpvv3u57)

3. [Guest / Headless Session Handling](#bookmark=id.9nf1eqkw7854)

4. [Agent Access Tiers & Step-Up Re-Authentication](#bookmark=id.kge9sul4pfbw)

5. [Database Design Implications](#bookmark=id.w45k8wjigxzg)

6. [Edge Cases & Failure Modes](#bookmark=id.m4gokm31g8un)

7. [Summary: Key Design Choices to Implement](#bookmark=id.d7z3e0rd153o)

8. [Resolved & Remaining Open Questions](#bookmark=id.5vyp98lkkjn6)

---

## **1\. Encryption Key Strategy**

### **Options Considered**

| Strategy | Description | Pros | Cons |
| :---- | :---- | :---- | :---- |
| **System-wide key** | One key encrypts all chats | Simple to implement | Single breach exposes everything; no per-user revocation |
| **Per-chat key** | Unique key per conversation | Maximum isolation | Key management hell at scale; no cross-chat search |
| **User-level key** ✅ | One key per user, all their chats encrypted with it | Rotatable per user; breach-contained; manageable | Slightly more complex vault setup than system-wide |

### **Recommended: User-Level Encryption**

Each authenticated OSU user is assigned a unique encryption key stored in a key management service (KMS). All of their chat records in the database store a reference to this key (not the key itself). Chat content is encrypted at rest using **AES-256**.

**Key lifecycle:** \- Key is generated on first login / account creation \- Key reference is stored alongside the user record \- Key rotation can happen per-user without touching any other user’s data \- On account deactivation or offboarding, revoking the key effectively renders all their chat data unreadable

**Recommended KMS — GCP or Azure (confirmed hosting):** \- **GCP:** Google Cloud KMS — integrates natively with Cloud Run, GKE, and Cloud SQL. Supports automatic key rotation and CMEK (Customer-Managed Encryption Keys) for Cloud SQL, which pairs directly with the chat DB. \- **Azure:** Azure Key Vault — integrates with AKS, App Service, and Azure Database for PostgreSQL. Supports key versioning and soft-delete for safe rotation. \- Either choice supports per-user key references and envelope encryption (data encrypted with a data encryption key, which is itself encrypted by the KMS-managed key).

### **Guest Encryption**

Guests (unauthenticated users) get an **ephemeral keypair** generated at session start:

* Private key lives in a sessionStorage entry or a secure HttpOnly session cookie

* Encrypted guest chats are stored with a TTL of **24 hours**, then purged

* If a guest authenticates mid-session, the ephemeral key is promoted: their session chat history is re-encrypted under their real user key and migrated transparently

---

## **2\. Session Authentication Timing**

### **Core Principle**

**Authenticate once at session start. Silently refresh. Only force re-auth for privileged agent access.**

### **Flow**

User arrives at OSU domain site  
        ↓  
FAB clicked → OpenBeavs loads  
        ↓  
Session gateway checks for OIDC token (OSU OAuth2 provider):  
  \- Valid OIDC id\_token present? → Validate with OSU JWKS endpoint  
    → Extract claims (sub, email, roles) → Issue OpenBeavs JWT  
    → Load user key ref from KMS  
  \- No token / expired? → Issue guest session with ephemeral key  
        ↓  
OpenBeavs JWT stored in memory (not localStorage — see Edge Cases)  
OIDC refresh token stored in HttpOnly secure cookie  
        ↓  
Silent background refresh every \~15 minutes via OIDC refresh flow  
        ↓  
Chat proceeds normally until agent handoff

### **OIDC Token Exchange**

OpenBeavs should not pass the raw OIDC id\_token to agents or store it. Instead:

1. Validate the OIDC id\_token against OSU’s JWKS endpoint on the OpenBeavs backend

2. Extract the relevant claims (sub, email, OSU role claim)

3. Issue a short-lived **internal OpenBeavs JWT** with only the claims needed for routing

4. All downstream agent calls use the internal JWT — the OIDC token never leaves the backend

### **JWT Design**

The internal OpenBeavs JWT should include:

{  
  "sub": "osu\_unique\_id",  
  "email": "beaver@oregonstate.edu",  
  "osu\_role": "student | staff | faculty | public",  
  "scope": \["public"\],  
  "key\_ref": "gcp-kms://projects/openbeavs/locations/us-west1/keyRings/users/cryptoKeys/abc123",  
  "session\_type": "authenticated | guest | a2a",  
  "source\_domain": "library.oregonstate.edu",  
  "exp": 1234567890,  
  "iat": 1234567890  
}

The osu\_role claim enables the Agent Router to surface role-appropriate agents (e.g. a staff admin agent should not be offered to students even if they’re in the authenticated scope). The source\_domain claim is used for cross-domain history isolation (see §5).

---

## **3\. Guest / Headless Session Handling**

### **Design Philosophy**

**Don’t block guests from chatting.** Generate the ephemeral keypair immediately and let them interact with public-tier agents. Only prompt for login if they attempt to access an agent that requires identity.

### **Guest Session Lifecycle**

Guest arrives  
      ↓  
Ephemeral keypair generated server-side  
      ↓  
Guest JWT issued (scope: \["public"\], session\_type: "guest", osu\_role: "public")  
      ↓  
Guest chats with public agents (campus maps, general FAQs, course catalog)  
      ↓  
Guest hits authenticated-tier agent (e.g. advising, library account)  
      ↓  
Inline login prompt appears in chat UI — redirects to OSU OIDC provider  
      ↓  
User authenticates via OSU OAuth2 / OIDC  
      ↓  
OIDC id\_token validated → role extracted (student / staff / faculty)  
Ephemeral key promoted → real user key assigned via GCP/Azure KMS  
Session chat history re-encrypted and migrated  
JWT upgraded with osu\_role and scope: \["authenticated"\]

**Note on public (non-OSU) users:** Members of the public who do not have an OSU identity will remain as guests permanently. They can only ever access public tier agents. Do not attempt to create shadow accounts for public users — keep them in the guest/ephemeral path.

### **Headless / A2A Agent Calls**

For automated A2A calls (agent-to-agent, no human in the loop):

* Require a **service account token** issued by OSU IT or the OpenBeavs admin

* Token carries its own scope and key reference

* Stored separately from user chat records; tagged session\_type: "a2a"

* No ephemeral key flow — must be pre-authenticated

### **Guest Data Retention Policy (Recommended)**

| Data | Retention |
| :---- | :---- |
| Guest chat messages | 24-hour TTL, then purged |
| Ephemeral key | Purged with session expiry |
| Guest session metadata | 24-hour TTL |
| Promoted guest chats (post-login) | Follow normal user retention policy |

---

## **4\. Agent Access Tiers & Step-Up Re-Authentication**

### **Three-Tier Access Model**

Define three access tiers in the Agent Registry. Every registered agent is tagged with one:

| Tier | Label | Who can access | OSU roles | Examples |
| :---- | :---- | :---- | :---- | :---- |
| 0 | public | Anyone, including guests | All (including public) | General FAQs, course catalog lookup, campus maps, event info |
| 1 | authenticated | Valid OSU OIDC login | Student, staff, faculty | Advising agent, library agent, course registration |
| 1+ | authenticated \+ role check | Valid OIDC \+ specific role | Staff only, or faculty only | HR tools (staff), grade submission (faculty) |
| 2 | privileged | Step-up MFA required | Student, staff, faculty | Student records, financial aid, admin tools |

### **Agent Routing & Scope Check**

The Agent Router performs a scope check **before any agent logic runs**:

User message arrives  
      ↓  
Agent Router matches intent → selects agent  
      ↓  
Router checks: agent.required\_tier vs jwt.scope  
      ↓  
Match? → Hand off to agent, proceed normally  
No match? → Return structured 401/403 before agent sees the message  
      ↓  
Frontend catches 401/403 → triggers step-up auth modal

**Do not check for access errors inside chat message content.** The scope check must happen at the routing layer, not by parsing what the agent says back. Parsing LLM output for security signals is fragile and bypassable.

### **Step-Up Authentication Flow**

When a privileged agent is requested and the user’s JWT only carries authenticated scope:

1. Router returns 403 Insufficient Scope

2. Frontend shows a non-dismissible modal: “This agent requires additional verification”

3. User completes MFA (TOTP, OSU Duo, etc.)

4. A short-lived **elevated token** is issued (e.g. 30-minute TTL, scope: \["authenticated", "privileged"\])

5. Original request is retried with the elevated token

6. Elevated token is not persisted after session ends

### **Re-Authentication for Guests Hitting Privileged Agents**

If a guest tries to access a privileged agent, the step-up flow must first complete a full login (not just MFA) before MFA is even presented. You cannot MFA your way into a privileged agent without a real identity attached.

---

## **5\. Database Design Implications**

### **Chat Record Schema (Conceptual)**

chats (  
  **id**              UUID **PRIMARY** **KEY**,  
  user\_id         UUID **REFERENCES** users(**id**),   *\-- NULL for guests*  
  guest\_session\_id UUID,                        *\-- NULL for authenticated users*  
  key\_ref         TEXT **NOT** **NULL**,                *\-- KMS key reference*  
  session\_type    ENUM('authenticated', 'guest', 'a2a'),  
  agent\_tier      ENUM('public', 'authenticated', 'privileged'),  
  content\_enc     BYTEA **NOT** **NULL**,               *\-- AES-256 encrypted blob*  
  created\_at      TIMESTAMPTZ **DEFAULT** now(),  
  expires\_at      TIMESTAMPTZ,                  *\-- NULL for authenticated, 24h for guest*  
  metadata        JSONB                         *\-- non-sensitive: agent\_id, domain, etc.*  
)

### **Key Points**

* content\_enc stores the fully encrypted conversation blob — never plaintext

* key\_ref points to KMS; the actual key never touches the DB

* metadata (agent ID, source domain, timestamp) can remain unencrypted for analytics/routing purposes — **do not put PII in metadata**

* Guest records use expires\_at; a background job purges them after TTL

* Promoted guest records: guest\_session\_id is cleared, user\_id is set, content\_enc is re-encrypted under the user key, expires\_at is nulled

---

## **6\. Edge Cases & Failure Modes**

### **6.1 JWT Stored Insecurely**

**Risk:** If JWT is stored in localStorage, XSS attacks can steal it. **Mitigation:** Store JWT in memory (JS variable) for the session lifetime. Use HttpOnly secure cookies for the refresh token. Never write JWTs to localStorage or sessionStorage.

### **6.2 KMS Downtime**

**Risk:** If the KMS is unavailable, no chats can be decrypted or written. **Mitigation:** \- Use KMS with high-availability SLAs (AWS KMS: 99.999%) \- Implement a graceful degradation mode: allow read-only access to cached decrypted content for in-flight sessions \- Queue write operations with a short retry window before surfacing an error

### **6.3 Guest Session Cookie Theft**

**Risk:** Stolen session cookie gives attacker access to ephemeral key and guest chat history. **Mitigation:** \- Use HttpOnly; Secure; SameSite=Strict on all session cookies \- Short TTL (24h) limits the blast radius \- Bind session to IP or User-Agent fingerprint as a secondary signal (soft check, not hard block — mobile IPs change)

### **6.4 Guest Promotes to Authenticated — Key Migration Failure**

**Risk:** If re-encryption fails mid-migration, the guest has lost their old session and their new account has no chat history. **Mitigation:** \- Run key migration in a transaction: don’t delete the ephemeral-encrypted version until the user-key-encrypted version is confirmed written \- If migration fails, keep the ephemeral session alive for another 24h and retry \- Surface a non-alarming message: “Your conversation history is still being linked to your account”

### **6.5 Privileged Agent Token Replay**

**Risk:** If an elevated token (step-up auth) is intercepted, an attacker could replay it within its TTL. **Mitigation:** \- Short TTL on elevated tokens (30 min max) \- Bind elevated tokens to the originating session ID \- One-time-use check: mark the elevated token as used in a fast cache (Redis) after first agent call; subsequent calls require fresh elevation

### **6.6 OSU SSO Outage**

**Risk:** If OSU’s SSO provider is down, no authenticated sessions can be created. **Mitigation:** \- Allow existing valid JWTs to continue operating (don’t re-validate against SSO on every request) \- Gracefully degrade new logins: show a “OSU login is temporarily unavailable, you can continue as a guest” message \- Do **not** fall back to a local password system — that creates a shadow identity problem

### **6.7 A2A Agent Impersonation**

**Risk:** A malicious actor crafts an A2A call pretending to be a trusted agent. **Mitigation:** \- All A2A service tokens must be pre-registered in the Agent Registry with a known public key \- Validate the A2A token signature on every call \- Rate-limit and audit-log all A2A calls by service account ID

### **6.8 Cross-Domain FAB Chat History — Isolated vs. Unified**

**The tradeoff:**

| Approach | Pros | Cons |
| :---- | :---- | :---- |
| **Unified history** | Continuity across sites; richer agent context | Library agent sees Registrar conversations; harder to justify institutionally; complex data governance |
| **Isolated per domain** | Clean data boundaries; easier OSU compliance; simpler to reason about | No context carry-over; repeated context-setting for users |
| **Isolated by default, opt-in sharing** ✅ | Best of both; user controls cross-domain context; defensible to OSU IT | Slightly more complex UI and session logic |

**Recommendation: Isolated by default, opt-in cross-domain context sharing.**

* Each FAB session’s source\_domain is stored in the JWT and on every chat record

* By default, the Agent Router only sees conversations from the current domain

* A user can explicitly say “use my conversation from the library site” — the router pulls that context with the user’s active consent

* On GCP: enforce this with Cloud SQL row-level security policies keyed on source\_domain; on Azure: use Row-Level Security in PostgreSQL Flexible Server

**Mitigation for the isolation case:** \- Store source\_domain on every chat record in metadata \- Agent Registry routing rules can be domain-scoped (a Registrar FAB only surfaces Registrar-relevant agents by default) \- No cross-domain reads happen without an explicit user-initiated action and a fresh scope check

### **6.9 LLM Response Contains Sensitive Data Leak**

**Risk:** An agent (especially a privileged one) returns PII or sensitive records in its response, which gets stored unintentionally in a lower-tier chat record. **Mitigation:** \- Tag the **chat record’s** agent\_tier at the highest tier accessed during that conversation \- Consider a PII scrubber pass on agent responses before storage (especially for public/authenticated tier chats) \- Audit logs for privileged agent responses should be access-controlled separately

### **6.10 Orphaned Encrypted Chats After Key Rotation**

**Risk:** If a user’s KMS key is rotated, their old chat records encrypted with the previous key version become inaccessible. **Mitigation:** \- Use KMS key **versioning** — both GCP Cloud KMS and Azure Key Vault support this natively. Old ciphertext is still decryptable with the old key version; new writes use the new version automatically. \- On GCP: set a key rotation schedule in Cloud KMS (e.g. 90 days); previous versions are kept as “enabled but not primary” — old data stays decryptable. \- On Azure: Key Vault key versions work the same way; set enabled: true on old versions until re-encryption is confirmed complete. \- Optionally run a background re-encryption job on rotation to migrate old records to the new key version — mark records with a key\_version field so the job can target only stale records. \- Never hard-delete old key versions until re-encryption is confirmed complete.

---

## **7\. Summary: Key Design Choices to Implement**

This section captures the concrete decisions you should commit to and build toward, updated for confirmed infrastructure (GCP/Azure, OAuth2/OIDC, mixed user base).

### **✅ Encryption: User-Level Keys via GCP Cloud KMS or Azure Key Vault**

* One encryption key per authenticated OSU user, managed in GCP Cloud KMS (preferred if on GCP) or Azure Key Vault

* Use **envelope encryption**: each chat is encrypted with a data encryption key (DEK); the DEK is encrypted by the KMS-managed key. Only the encrypted DEK is stored in the DB.

* Guests get a temporary ephemeral key generated server-side, stored in a secure HttpOnly cookie, with a 24-hour TTL

* All chat content stored as AES-256 encrypted blobs; key references (not keys) stored in the DB

* Key rotation uses KMS versioning — old versions stay decryptable; new writes use the latest version automatically

### **✅ Authentication: OIDC Token Exchange → Internal JWT, Silent Refresh**

* Validate OSU OIDC id\_token on the OpenBeavs backend against OSU’s JWKS endpoint

* Extract role claims (student, staff, faculty) — never pass the raw OIDC token to agents

* Issue a short-lived internal OpenBeavs JWT with: sub, osu\_role, scope, key\_ref, source\_domain

* Store internal JWT **in memory only** — not localStorage; store OIDC refresh token in HttpOnly; Secure; SameSite=Strict cookie

* Silent background OIDC refresh every \~15 minutes

* Force re-authentication **only** when a user attempts to access a privileged tier agent

### **✅ Guest & Public User Sessions: Unblocked Entry, Inline Promotion**

* Never block a guest or public user from chatting — generate ephemeral key and guest JWT immediately

* Public (non-OSU) users permanently stay in the guest/public scope path — do not create shadow accounts

* Guest chats expire after 24 hours; a background purge job handles cleanup

* When a guest with a valid OSU identity hits an authenticated agent, show an **inline login prompt** (not a page redirect) that triggers the OIDC flow

* On successful OIDC login, migrate and re-encrypt their session history under their real user key atomically

### **✅ Agent Registry: Three-Tier Access \+ Role-Scoped Agents**

* Tag every registered agent with: public, authenticated, or privileged

* For staff/faculty-only tools, add a required\_role field alongside required\_tier in the Agent Registry schema

* Scope check at the **Agent Router layer** — before any agent logic runs — validates both scope and osu\_role against the agent’s requirements

* Return a structured 401/403 on scope mismatch; frontend catches this and triggers the appropriate response (login prompt, step-up MFA modal, or “access denied” message)

* Do not rely on parsing agent response content to detect authorization errors

### **✅ Step-Up Auth: Short-Lived Elevated Tokens, MFA via OSU Duo**

* Step-up triggers a non-dismissible MFA modal (OSU Duo is the likely MFA provider for OSU-identity users)

* Issues a short-lived elevated token (30-minute TTL, bound to session ID)

* Track elevated token use in a fast cache (GCP Memorystore / Azure Cache for Redis) — one-time-use flag

* Guests must complete full OIDC login before MFA for any privileged agent access

### **✅ Cross-Domain Chat History: Isolated by Default, Opt-In Sharing**

* Store source\_domain on every chat record and in every JWT

* Each FAB session is scoped to its originating OSU domain by default — no cross-domain reads happen automatically

* Implement opt-in: a user can explicitly request cross-domain context; the router fetches it with a fresh scope check and user-visible consent step

* Enforce domain isolation at the DB layer: GCP Cloud SQL row-level security or Azure PostgreSQL RLS policies keyed on source\_domain

* Agent Registry routing rules should be domain-aware — a Registrar FAB should not surface Library-only agents by default

### **✅ Database: Envelope Encryption, Domain Scoping, Guest Purge**

* Store encrypted DEK \+ ciphertext blob in the chat record; never plaintext content

* Keep non-PII metadata (agent\_id, source\_domain, agent\_tier, timestamps) unencrypted for routing and analytics

* Add a key\_version field to each chat record to support targeted re-encryption after key rotation

* Background job purges guest records after 24-hour TTL

* Tag each chat record with agent\_tier reflecting the highest-access agent touched in that conversation

---

---

## **8\. Resolved & Remaining Open Questions**

### **Resolved**

| Question | Answer | Impact |
| :---- | :---- | :---- |
| SSO/identity system | OAuth2 / OIDC | Internal JWT exchange pattern; JWKS validation on backend |
| Hosting platform | GCP or Azure | GCP Cloud KMS or Azure Key Vault; matching DB RLS tooling |
| Primary user types | Students, staff, faculty, and public guests | Three-tier \+ osu\_role claim on JWT; permanent guest path for public |
| Cross-domain history | Isolated by default, opt-in sharing | source\_domain in JWT \+ DB; DB-layer RLS enforcement |

### **Still Open**

1. **GCP vs Azure — which one?** The KMS, DB, and caching choices differ slightly. Locking this in early will simplify the implementation plan.

2. **OSU OIDC discovery endpoint** — What is the OSU OAuth2 provider’s .well-known/openid-configuration URL? This is needed to configure JWKS validation and refresh flows.

3. **Open WebUI fork auth layer** — Does the current Open WebUI fork already have a session/auth middleware layer, or is that being built from scratch? This determines where OIDC token exchange and KMS calls get wired in.

4. **Agent Registry schema** — Is the Agent Registry already built, or still conceptual? The required\_tier, required\_role, and source\_domain routing fields need to be first-class fields in the registry schema from the start.

5. **OSU institutional data retention policy** — Does OSU IT or legal require a minimum retention period for authenticated chat records, or prohibit retention beyond a certain window? This would override or constrain the guest 24-hour TTL and authenticated chat storage approach.

6. **Privileged agent candidates** — What specific systems are planned for the privileged tier (e.g. Banner integration, financial aid, HR systems)? Knowing this validates whether the single step-up token model is sufficient, or whether per-agent scope claims are needed.