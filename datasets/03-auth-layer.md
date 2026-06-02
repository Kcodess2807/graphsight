# AuthLayer — Service Reference

`AuthLayer` is ShopFlow's identity and access service. It handles login, issues
and validates JSON Web Tokens (JWTs), and manages session state. Nearly every
authenticated request in the platform passes through it.

- **Canonical name:** `AuthLayer`
- **Repository:** `auth-layer`
- **Owning team:** Identity
- **Tech lead:** Priya Nair
- **Language / runtime:** Go 1.22
- **Datastores:** `UserDB` (credentials + sessions)

## Responsibilities

- Authenticate username/password and federated logins.
- Issue short-lived access tokens and longer-lived refresh tokens.
- Validate tokens on behalf of `APIGateway` and `PaymentService`.
- Track active sessions and support forced logout / revocation.

## Dependencies

| Depends on  | Purpose                                  | Failure mode if unavailable          |
|-------------|------------------------------------------|--------------------------------------|
| `UserDB`    | Credential lookup, session reads/writes  | Logins and token validation fail     |

`AuthLayer` has exactly one hard dependency: `UserDB`. When `UserDB` is slow or
refusing connections, `AuthLayer` cannot validate tokens, which causes a
platform-wide authentication outage even if every other service is healthy.

## Token Validation Path

1. `APIGateway` (or `PaymentService`) presents a JWT to `AuthLayer`.
2. `AuthLayer` verifies the signature locally, then checks the session record in
   `UserDB` to confirm the token has not been revoked.
3. A `UserDB` lookup that exceeds the 2s timeout is treated as a validation
   failure, and the request is rejected (fail closed).

## Connection Pool

`AuthLayer` maintains its own pool against the shared `UserDB` primary:

```yaml
userdb:
  max_open_conns: 25
  max_idle_conns: 10
  conn_max_lifetime: 30m
  query_timeout: 2s
```

Because the pool is sized against the same 100-connection `UserDB` primary used
by `PaymentService`, the two services must coexist within that budget. If a
neighbor service consumes its full share and then leaks beyond it, `AuthLayer`
starts receiving connection-refused errors from `UserDB`.

## SLOs

- Availability: 99.99% monthly (highest tier — it gates everything else)
- p99 token validation latency: < 50 ms
