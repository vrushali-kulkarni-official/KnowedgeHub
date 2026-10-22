# ─────────────────────────────────────────────────────────────────
#  bao agent configuration (Level 7, §7.2 — Option B)
#
#  The agent authenticates to OpenBao with AppRole, renews the token,
#  and renders secrets to files that the app reads. The app never
#  handles an OpenBao token at all.
# ─────────────────────────────────────────────────────────────────

pid_file = "/tmp/bao-agent.pid"

vault {
  address = "https://openbao:8200"
  ca_cert = "/openbao/certs/ca.crt"

  retry {
    num_retries = 5
  }
}

auto_auth {
  method "approle" {
    mount_path = "auth/approle"
    config = {
      role_id   = "REPLACE_WITH_ROLE_ID"
      secret_id = "REPLACE_WITH_SECRET_ID"
    }
  }

  # Write the token to a file the app can read
  sink "file" {
    config = {
      path = "/secrets/openbao-token"
      mode = 0640
    }
  }
}

template {
  source               = "/secrets/openbao-token"
  destination          = "/secrets/openbao-token"
  error_on_missing_key = true

  wait {
    min_duration = "5s"
    max_duration = "5m"
  }
}
