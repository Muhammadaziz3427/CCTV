---
name: clerk-auth-migration
description: Migrate user authentication from Replit Auth to Clerk, including data migration and code changes.
---

# Clerk Auth Migration

Full migration flow from Replit Auth to Clerk, covering user confirmation, data migration, and code changes.

## When to Use

- User asks to migrate from Replit Auth to Clerk
- Agent receives a special message indicating the User clicked "Update now" in the Auth pane migration banner

## Step 1: Confirm with User

Before proceeding, call the `AskQuestion` model tool to get explicit confirmation:

```json
{
  "question": "Migrating from Replit Auth to Clerk will create a new Clerk app, copy over your Replit Auth users, and update your application code to use Clerk. Would you like to proceed?",
  "choices": ["Yes, proceed", "No"]
}
```

If the user does not choose "Yes, proceed", stop and do not call any migration callback.

If the user declines, stop and do not proceed.

## Step 2: Provision Clerk App

Use the `codeExecution` tool to call `setupClerkWhitelabelAuth` to create the Clerk app and set secrets:

```javascript
const result = await setupClerkWhitelabelAuth();
console.log(result);
```

This creates the Clerk application, enables SSO providers, and sets `CLERK_SECRET_KEY`, `CLERK_PUBLISHABLE_KEY`, and `VITE_CLERK_PUBLISHABLE_KEY` as environment secrets.

## Step 3: Migrate User Data

**Before calling any migration function**, tell the user: "Starting user data migration — this may take several minutes depending on how many users you have. I'll check progress periodically and let you know when it's done."

### 3a. Start the migration

Use the `codeExecution` tool to kick off the migration workflow:

```javascript
const result = await migrateReplitAuthToClerk();
console.log(result);
```

This returns immediately after starting a background workflow that copies all Replit Auth users to Clerk (preserving passwords, emails, usernames). It does **not** wait for completion.

- If `result.success` is `false`, report the error to the user and stop.

### 3b. Poll for completion

After starting, poll for completion using `pollClerkMigration`. Each call polls internally for up to 9 minutes, returning early if a terminal status is reached.

```javascript
const result = await pollClerkMigration();
console.log(result);
```

Returns `{ success, status, totalUsers, error }`.

Call this in a loop across **separate** `codeExecution` calls (**max 3 attempts**). Between each call, briefly update the user (e.g. "Still migrating, checking again…").

- `result.status === "data_migration_completed"` — report `result.totalUsers` users migrated and proceed to Step 4.
- `result.status === "failed"` — report `result.error` to the user and stop. Do not proceed with code migration.
- `result.status === "in_progress"` — migration is still running. Call `pollClerkMigration` again in a new `codeExecution` session.

If the migration has not completed after **3 poll attempts** (~27 minutes), stop and tell the user the migration is taking longer than expected and may need manual investigation. Do **not** proceed with code migration.

## Step 4: Migrate Code

### Required preflight: verify data migration is complete

Before making any code changes, use the `codeExecution` tool to query the current migration status:

```javascript
const status = await getClerkMigrationStatus();
console.log(status);
```

Start code migration only if `status.status === "data_migration_completed"`.

The goal of code migration is to **swap the identity provider while preserving the app's structure**. The users table, the bridge between auth and local data, the authorization logic — all of that stays the same. Only the login/session machinery changes.

Apply code changes based on what the app uses:

- **For web artifacts (server + client)**: Read and follow `references/web-migration.md`.
- **For Expo mobile artifacts**: Read and follow `references/expo-migration.md`.

## General Rules

1. **Read `setup-and-customization.md` before writing any new Clerk code, and copy its canonical wiring verbatim** — `clerkPubKey` (`publishableKeyFromHost(...)`), `clerkProxyUrl` (unconditional), `<ClerkProvider>` props, server `clerkMiddleware`, and the `/sign-in/*?` / `/sign-up/*?` route paths. It also contains critical implementation patterns (proxy middleware ordering, routing, theming) that will silently break the app if missed. Do not "improve" or restate these blocks from prior Clerk knowledge — theme/UI is the only part to customize. The migration references cover only what to remove and how to map Replit Auth patterns to Clerk equivalents.

2. **Web and mobile use different auth transports — never mix them.**
   - **Web (React + Express): cookies only.** The browser sends Clerk's session cookie to same-origin API requests. Do not add `getToken()`, `setAuthTokenGetter`, `Authorization: Bearer`, or any other explicit token handling to web requests.
   - **Mobile (Expo/native): bearer tokens only.** Mobile has no browser cookie jar, so Expo must attach a Clerk token through the generated API client's mobile token hook.

   If a web request returns 401, do not "fix" it by adding tokens. Debug cookie/session loading, middleware ordering, `requireAuth`, local-user bridge/JIT provisioning, or authorization state instead.

## Build Rules

1. **Do NOT drop the `users` table or `sessions` table.** Leave existing database tables and schema definitions in place. The `users` table remains active for app-specific data (roles, permissions, relationships, preferences). Clerk owns identity and authentication; the local DB owns authorization and app state.

   **Keep all FK constraints intact.** Do not remove `.references(() => usersTable.id)`, `.references(() => usersTable.email)`, `.references(() => usersTable.username)`, or any other FK pointing to the users table. Keep schema changes minimal.

   **Identity columns that are FK targets** (e.g., other tables reference `usersTable.email` or `usersTable.username`): keep populating them from `sessionClaims` during JIT upsert. The values are available in the session token.

   **Identity columns that are NOT FK targets**: stop populating them. Leave the column in the schema but don't write to it.

   **App columns** (role, permissions, relationships, etc.): continue populating as normal.

   Remove the old `upsertUser` logic that synced identity data on every login. Replace it with JIT provisioning that creates or finds a local row on the user's first authenticated request (see `references/web-migration.md` step 4).

2. **Do NOT use "Replit" or "Replit Auth" in user-facing UI text** after migration.

3. **Follow the strict web API call guidance from `references/web-migration.md`.** Web API calls must go through the app's canonical fetch path (`customFetch` from `@workspace/api-client-react` / generated API client) so cookies and shared auth/error handling are applied consistently. Do not leave direct `fetch()` calls or custom wrappers that can bypass cookies.

4. **Remove the `@workspace/replit-auth-web` package** if it exists (`lib/replit-auth-web/`). Remove it from root and artifact `tsconfig.json` references, artifact `package.json` dependencies, then delete the directory.

5. **Clean up OpenAPI spec** if the project uses `lib/api-spec/openapi.yaml`. Remove auth endpoint definitions (`/login`, `/callback`, `/logout`, `/auth/user`, `/mobile-auth/token-exchange`, `/mobile-auth/logout`) and re-run codegen:

   ```bash
   pnpm --filter @workspace/api-spec run codegen
   ```

6. **Update `replit.md`** to reflect that authentication now uses Clerk instead of Replit Auth.

## User Identity Mapping

**Note on user IDs for migrated users:** the React `user.id` from `useUser()` is Clerk's native ID (e.g. `user_2abc...`). For users carried over from the Replit Auth migration, the original Replit Auth ID is preserved on `user.externalId`. Use `user.externalId ?? user.id` whenever the frontend compares against application data keyed by the legacy ID (e.g. `project.ownerId === user?.id` would silently break for migrated users). On the server, use `sessionClaims` — see the CRITICAL notes below.

### Server-side: use `sessionClaims` for everything

The session token is pre-configured with identity fields. Use these directly — **do NOT call `clerkClient.users.getUser()` in the request path.**

| Replit Auth | Clerk (server via `sessionClaims`) | Clerk (React) |
| --- | --- | --- |
| `req.user.id` | `auth.sessionClaims.userId` / `req.dbUser.id` | `user.externalId ?? user.id` via `useUser()` |
| `req.user.email` | `auth.sessionClaims.email` | `user.primaryEmailAddress?.emailAddress` |
| `req.user.firstName` | `auth.sessionClaims.firstName` | `user.firstName` |
| `req.user.lastName` | `auth.sessionClaims.lastName` | `user.lastName` |
| `req.user.profileImageUrl` | `clerkClient.users.getUser(auth.userId).imageUrl` (only if needed — not in session token) | `user.imageUrl` |
| `req.isAuthenticated()` | `requireAuth` middleware (rejects unauthorized requests automatically) | `isSignedIn` via `useAuth()` |
| `useAuth()` from `@workspace/replit-auth-web` | N/A | `useUser()` / `useAuth()` from `@clerk/react` |

**CRITICAL — Two different IDs exist in the session. Never confuse them:**

| Field | What it is | Use for |
| --- | --- | --- |
| `auth.sessionClaims.userId` | Legacy Replit subject ID (preserved as Clerk externalId for migrated users; Clerk native ID for new users) | Local DB lookups — see `web-migration.md` step 4 for the bridge-specific lookup pattern |
| `auth.userId` | Clerk's native ID (`user_2abc...`) | **Clerk API calls ONLY** (e.g., `clerkClient.users.getUser()`) |

**Never pass `sessionClaims.userId` to Clerk API methods** — it's a legacy UUID/numeric ID, not a Clerk ID. Clerk will return a 404. Use `auth.userId` exclusively for Clerk API calls.

**Never pass `auth.userId` to local DB queries for migrated users** — it's a Clerk-native ID that doesn't match any existing row. Use `sessionClaims.userId` for local DB lookups.

In practice, you should rarely need `auth.userId` at all — `sessionClaims` has everything needed for the bridge and basic identity display (email, username, firstName, lastName).

## Step 5: Restart Workflows

Restart **every** workflow the migration touched (server, web, Expo if present) and confirm each comes up without errors.
