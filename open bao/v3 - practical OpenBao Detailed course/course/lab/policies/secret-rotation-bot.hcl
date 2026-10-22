# Meridian AI - the automated secret rotation bot
#
# The ONLY identity permitted to write secrets.
# Rotation is separated from reading on purpose: a read-only service can
# never corrupt a secret by accident.
#
# Note: "delete" (soft delete, recoverable) is granted, but "destroy"
# (irreversible) is NOT. Destroying a secret should require a human.

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
