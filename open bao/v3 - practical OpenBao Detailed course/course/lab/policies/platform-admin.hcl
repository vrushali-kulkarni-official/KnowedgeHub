# Meridian AI - human administrator
#
# Everything EXCEPT the operations that require `sudo`:
#   - seal / unseal
#   - root token generation
#   - authoring policies
#
# This is the most important policy in the set. `root` in human hands means
# one compromised admin session compromises every secret in the company.
# The `sudo` capability is what makes break-glass a DELIBERATE, auditable act.

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
