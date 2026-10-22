Unseal Key: Tvf5Z/6UlKIEqdvuCeCJSG/T7gvoZYQ7daGIEqLZ7E0=
Root Token: root


### Basic Commands:

1. bao secrets enable -path=secret kv-v2
2. bao kv put -mount=secret myapp db_password="s3cr3t" api_key="abc123"
3. bao kv get -mount=secret myapp

4. bao policy write policy-name - <<'EOF'
path "secret/data/myapp" {
  capabilities = ["read"]
}
EOF

5. bao write 
6. bao read 

7. bao status
8. bao version

9. bao operator init -key-shares=5 -key-threshold=3


```
export BAO_ADDR=http://127.0.0.1:8200
export BAO_TOKEN=dev-root-token
```

### Keys:
`unseal share(s) → root key → encryption key → plaintext`

### Storage backends:
1. raft (integrated storage) (supports HA)
2. postgresql (supports HA)
3. pebbledb (No HA)
4. `in-memory` (No HA)
5. file (REMOVED in 2.7.0.)

#### PostgreSQL config:
```hcl
storage "postgresql" {
  connection_url = "postgres://bao:bao@postgres:5432/openbao?sslmode=verify-full"
  ha_enabled     = "true"
  cluster_addr   = "https://10.0.0.1:8201"   # needed for 2.7 read-scaling
}
```

 ### State
1. Uninitialized (Never `bao operator init`)
2. Initialized + Sealed
3. Initialized + Unsealed
4. Unsealed + Standby

### Shamir seal
1. bao operator init -key-shares=5 -key-threshold=3
2. bao operator init -recovery-shares=5 -recovery-threshold=3

### Unsealing
1. bao status                      # -> Sealed: true
2. bao operator unseal <share-1>   # "Key 1 of 3 unsealed"
3. bao operator unseal <share-2>   # "Key 2 of 3 unsealed"
4. bao operator unseal <share-3>   # "Unseal complete"
5. bao status                      # -> Sealed: false

### Sealing
bao operator seal 

### Generating a new root token
bao operator generate-root -init
bao operator generate-root -format=json

---

## Policies

```hcl
	
# app-readonly.hcl
path "secret/data/myapp" {
  capabilities = ["read"]
}
```

#### The nine capabilities

| Capability | Means                                          | HTTP verb                           |
| ---------- | ---------------------------------------------- | ----------------------------------- |
| `create`   | Create a new object at this path               | `POST`/`PUT`                        |
| `read`     | Read the value                                 | `GET`                               |
| `update`   | Overwrite an existing value                    | `POST`/`PUT`                        |
| `patch`    | Partially modify                               | `POST`/`PUT` (merge)                |
| `delete`   | Delete                                         | `DELETE`                            |
| `list`     | List entries under a path                      | `LIST`/`GET ?list=true`             |
| `scan`     | Recursively list                               | `LIST`/`GET ?list=true` (recursive) |
| `sudo`     | Perform the action *as if* holding root        | any                                 |
| `deny`     | Explicitly deny (overrides any wildcard grant) | —                                   |

---

## Token

### Token model

```
   Login (auth method)  ──▶  Token
                              ├── policies: ["app-readonly", "default"]
                              ├── TTL: 1h, renewable
                              ├── parent: <the token that created it>
                              ├── accessor: 6f1c...  (safe to store & log)
                              └── metadata: {username: "bob"}
```



### Token Commands
bao token create -policy=app-readonly -ttl=1h -orphan=true
bao token revoke -accessor <accessor>
bao token renew

#### Token Life

bao token create -policy=app -ttl=1h -renewable=true -explicit-max-ttl=24h

bao token create -policy=app -period=24h 

---

# Audit
Every request and every response is written to **every enabled audit device**.
``` hcl

audit "file" "file" {
  description = "Local audit log (declarative)."
  options {
    file_path = "/openbao/logs/audit.log"
    mode      = "0600"
    log_raw   = "false"
  }
}
```


The audit log is a structured record:

```json
{
  "type": "response",
  "auth": { "client_token": "hmac-sha256:...", "policies": ["app-readonly"] },
  "request": { "id": "...", "client_token": "hmac-sha256:...", "operation": "read",
               "path": "secret/data/myapp" },
  "error": "",
  "response": { "data": { "data": { "api_key": "hmac-sha256:..." } } },
  "auth": { "display_name": "token", "policies": ["app-readonly"] }
}
```


---

## 1.9 Identity — entities, aliases, groups

```
  Entity (a person or machine, namespace-scoped)
    ├── Alias  (how it logs in: auth method + metadata)
    ├── Group  (a named bucket of entities)
    │     └── Policies
    └── Metadata
```


#### Create an entity + alias:

```bash
# Create an entity + alias
bao write identity/entity name="alice" \
    metadata=full_name="Alice Smith" \
    policies=app-readonly

bao write identity/entity-alias \
    name="alice" \
    canonical_id=$(bao read -field=id identity/entity/name/alice) \
    mount_accessor=$(bao auth accessor list -format=json | jq -r '.[]|select(.path=="auth/userpass/").accessor')
```


#### Groups:

```bash
bao write identity/group name=platform \
    policies=app-readonly,app-admin

bao write identity/entity/id/<id> \
    groups=platform
```

#### Auth method
