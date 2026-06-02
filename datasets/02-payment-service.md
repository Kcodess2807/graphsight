# PaymentService — Service Reference

`PaymentService` is the system of record for all money movement on ShopFlow. It
authorizes, captures, and refunds payments, and is the only service permitted to
communicate with the external payment provider (PSP).

- **Canonical name:** `PaymentService`
- **Repository:** `payment-service`
- **Owning team:** Payments Squad
- **Tech lead:** Alex Chen
- **Language / runtime:** Java 17 / Spring Boot
- **Datastores:** `UserDB` (billing + account reads), internal Postgres (ledger)

## Responsibilities

- Authorize and capture card payments via the external PSP.
- Issue refunds and partial refunds.
- Re-validate the caller's JWT with `AuthLayer` before any money movement.
- Read billing address and stored payment methods from `UserDB`.
- Maintain an internal double-entry ledger for reconciliation.

## Dependencies

| Depends on    | Purpose                                | Failure mode if unavailable        |
|---------------|----------------------------------------|------------------------------------|
| `AuthLayer`   | Token re-validation                    | Payments rejected (fail closed)    |
| `UserDB`      | Billing details, stored cards          | Authorization cannot proceed       |
| PSP (external)| Card authorization and capture         | Payments queued / retried          |

## Database Connection Pool

`PaymentService` connects to `UserDB` through a HikariCP connection pool. The
pool is sized conservatively because `UserDB` is shared with `AuthLayer`.

```yaml
# config/datasource.yml (production)
userdb:
  jdbcUrl: jdbc:postgresql://userdb-primary:5432/users
  maximumPoolSize: 20        # hard cap — UserDB primary allows 100 total
  maxLifetime: 1800000       # 30 min — recycle connections to avoid leaks
  connectionTimeout: 3000    # fail fast rather than queue indefinitely
  readOnly: false
  targetReplica: userdb-replica   # reads should prefer the replica
```

> **Operational note:** Any change to `maximumPoolSize`, `maxLifetime`, or the
> target host requires review by the `UserDB` owner (Platform). Removing
> `connectionTimeout` or raising the pool size can exhaust the shared `UserDB`
> primary and take down `AuthLayer` as a side effect.

## Key Endpoints

- `POST /v1/payments/authorize`
- `POST /v1/payments/capture`
- `POST /v1/refunds`
- `GET  /v1/payments/{id}`

## SLOs

- Availability: 99.95% monthly
- p99 authorization latency: < 400 ms
- Error budget burn alerts page the Payments Squad on-call.
