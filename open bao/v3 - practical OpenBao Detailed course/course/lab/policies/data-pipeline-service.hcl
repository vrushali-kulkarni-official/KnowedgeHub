# Meridian AI - the data pipeline service
#
# Reads database and cache credentials. Nothing else.

path "ai/platform/data/db/postgres" {
  capabilities = ["read"]
}

path "ai/platform/data/cache/redis" {
  capabilities = ["read"]
}

path "ai/platform/metadata/db/postgres" {
  capabilities = ["read"]
}
