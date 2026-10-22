# Meridian AI - human operator (OIDC login, Module 05)
#
# Read + browse, but NO write on secrets.
# Write stays with the rotation bot and the security team.

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
