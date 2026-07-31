# # Database (sql Alchemy )

1. sql alchemy 2.0 --> mapped[]

2. use ORM

3. primary key (Auto-incrementing)

4. data type

5. every field has constraints (nullable, default, non negative, foriegn key)

6. max character limit for fields like username, password, email id, etc

### other Imp fields in table in DB:

1. Logging:  time stamp needed (server_default=func.now()  ) (`timezone=True`)

2. Is user active (Never delete always disable)

3. String representation (for debugging)

### SQL ORM Query:

1. Is SQLAlchemy 2.0 style used? (`db.execute(select(...)).scalars().all()` not legacy `db.query(...)`)
2. Are relationships defined with proper `back_populates`?
3. Is `lazy="selectin"` or explicit `joinedload` used to avoid N+1 queries?
4. Are session lifetimes managed correctly? (One per request, closed at end)

# Pydantic Fast API

1. separate class for each api call

2. add constraints and default values (password: str | None = Field(None, min_length=8, max_length=128))

3. use pydantic special data types like `EmailStr`, `HttpUrl`, `PostgresDsn`, NonNegativeInt, SecretStr, FutureDate

4. Check return datatypes(it should be a pydantic class name)

5. check if proper error is returned e.g., `{"error": {"code": "...", "message": "..."}}`)

6. chekc if status codes are used correctly

7. use /api/v1/users

8. use summary and description in FastAPI while defining api endpoint routes

9. add middleware with constraints CORSMiddleware, allow_methods=["GET", "POST", "PUT", "DELETE"], allowed allow_headers=[], allow_credentials=False

# JWT

1. use strong algorithm
   
   1. str = "HS256" if its small application and you control everything
   
   2. str = "RS256" if its large application and you dont control everything(3rd party apps/tools)

# .env

1. check it secrets are used via OS enviroment and not directly by accessing the file

# Cryptography

1. use argon2id instread of bcrypt to store passwords
   
   1. | Part           | Meaning                     |
      | -------------- | --------------------------- |
      | `$argon2id`    | Algorithm variant           |
      | `v=19`         | Argon2 version (0x13)       |
      | `m=65536`      | Memory cost in KiB (64 MiB) |
      | `t=3`          | Time cost (3 iterations)    |
      | `p=1`          | Parallelism (1 lane/thread) |
      | `<Base64Salt>` | Random 16-byte salt         |
      | `<Base64Hash>` | 32-byte derived key         |

| Check                 | Correct Value                                                                                                                                                       |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Algorithm             | `HS256` (symmetric, single service) or `RS256` (asymmetric, multiple services)                                                                                      |
| Secret key            | At least 32 random bytes, from env, never hardcoded                                                                                                                 |
| Access token expiry   | **15 minutes** (industry standard)                                                                                                                                  |
| Refresh token expiry  | **7 to 30 days** (longer = more risk)                                                                                                                               |
| Claims included       | `sub` (user id), exp, iat, jti (unique id for revocation), plus iss and aud (always validate them). Keep payload minimal — never put sensitive data in the JWT      |
| Refresh token storage | Hashed in DB (so a DB leak doesn’t give attackers valid tokens). For browser clients store in HttpOnly + Secure + SameSite=Strict (or Lax) cookie                   |
| Token rotation        | New refresh token issued on each refresh; old one immediately invalidated. Detect reuse of an already-rotated token → revoke the entire token family (theft signal) |
| Logout                | Refresh token revoked in DB (access token expires naturally)                                                                                                        |

** 
