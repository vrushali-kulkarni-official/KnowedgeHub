# =============================================================================
# Meridian AI - Least-privilege policies for the OpenBao course
# =============================================================================
# Apply with:
#   bao policy write <name> - < policies/<policy-name>.hcl
#
# Every policy here maps to a real Meridian AI service. The point of these
# examples is that each one grants the MINIMUM needed for a specific job,
# and no more.
# =============================================================================


# -----------------------------------------------------------------------------
# ai-harness-service - the FastAPI/LangChain app
# -----------------------------------------------------------------------------
# The app needs exactly one secret: the Gemini API key. It must not be able
# to read the database password, the Redis password, or list what else
# exists on the platform.
#
# Note: there is NO "list" capability anywhere. The app knows the exact
# path of the one secret it needs. If it needed to discover secrets
# dynamically, that would be a design smell.
# -----------------------------------------------------------------------------
path "ai/platform/data/llm/gemini" {
  capabilities = ["read"]
}

path "ai/platform/metadata/llm/gemini" {
  capabilities = ["read"]
}

# Deliberately NOT granted:
#   - list on ai/platform/metadata/llm  (would reveal secret names)
#   - read on ai/platform/data/db/*     (not this service's business)
#   - update/delete                     (rotation is a separate job)


# -----------------------------------------------------------------------------
# data-pipeline-service - reads DB + cache credentials
# -----------------------------------------------------------------------------
path "ai/platform/data/db/postgres" {
  capabilities = ["read"]
}

path "ai/platform/data/cache/redis" {
  capabilities = ["read"]
}

path "ai/platform/metadata/db/postgres" {
  capabilities = ["read"]
}


# -----------------------------------------------------------------------------
# secret-rotation-bot - the only identity allowed to WRITE secrets
# -----------------------------------------------------------------------------
# Rotation is separated from reading on purpose. A service that can only
# read can never accidentally corrupt a secret; a service that can write is
# isolated to the rotation job.
#
# `update` = create a new version. `delete` = soft delete (recoverable).
# We grant delete but NOT destroy, because destroying a secret is
# irreversible and should require a human.
# -----------------------------------------------------------------------------
path "ai/platform/data/llm/*" {
  capabilities = ["create", "update", "read", "delete"]
}

path "ai/platform/metadata/llm/*" {
  capabilities = ["read", "update"]
}

path "ai/platform/data/db/*" {
  capabilities = ["create", "update", "read", "delete"]
}

path "ai/platform/metadata/db/*" {
  capabilities = ["read", "update"]
}


# -----------------------------------------------------------------------------
# platform-operator - human access via OIDC (Module 05)
# -----------------------------------------------------------------------------
# Humans get read + list so they can browse. They do NOT get write on
# secrets; that stays with the rotation bot and the security team.
# -----------------------------------------------------------------------------
path "ai/platform/data/*" {
  capabilities = ["read", "list"]
}

path "ai/platform/metadata/*" {
  capabilities = ["read", "list"]
}

path "sys/audit" {
  capabilities = ["read"]
}

path "sys/policy" {
  capabilities = ["read", "list"]
}


# -----------------------------------------------------------------------------
# platform-admin - human administration
# -----------------------------------------------------------------------------
# Everything the operator can do EXCEPT the things that require `sudo`:
# seal/unseal, root token generation, and policy authoring.
#
# This is the single most important policy in the file. `root` is a footgun
# in human hands: one compromised admin session = full compromise of every
# secret. The `sudo` capability is what lets you deliberately break glass.
# -----------------------------------------------------------------------------
path "ai/platform/data/*" {
  capabilities = ["create", "read", "update", "delete", "list"]
}

path "ai/platform/metadata/*" {
  capabilities = ["create", "read", "update", "delete", "list"]
}

path "ai/transit/*" {
  capabilities = ["create", "read", "update", "delete", "list"]
}

path "sys/audit" {
  capabilities = ["read", "list"]
}

path "sys/mounts" {
  capabilities = ["read", "list"]
}

path "sys/auth" {
  capabilities = ["read", "list"]
}

path "sys/policy" {
  capabilities = ["read", "list"]
}

path "sys/capabilities-self" {
  capabilities = ["update"]
}
