# UserDB — Datastore Reference

`UserDB` is the authoritative datastore for customer accounts, credentials, and
profiles. It is a shared resource: both `AuthLayer` and `PaymentService` read
from it on the critical path, which makes it the platform's most contended
dependency.

- **Canonical name:** `UserDB`
- **Repository (schema + migrations):** `user-db`
- **Owning team:** Platform
- **Owner / DBA:** Jordan Lee
- **Engine:** PostgreSQL 15
- **Topology:** 1 primary (`userdb-primary`) + 1 read replica (`userdb-replica`)

## What It Stores

- `accounts` — customer identities and status
- `credentials` — password hashes, MFA enrollment
- `sessions` — active session and refresh-token records
- `billing_profiles` — billing addresses and stored payment method references

## Connection Budget

The `UserDB` primary is configured with a hard ceiling:

```ini
# postgresql.conf (userdb-primary)
max_connections = 100
```

This budget is shared across all clients:

| Client            | Allocated pool size | Notes                                  |
|-------------------|---------------------|----------------------------------------|
| `AuthLayer`       | 25                  | Validation is read-heavy               |
| `PaymentService`  | 20                  | Should prefer the replica for reads    |
| Batch / migrations| 10                  | Off-peak only                          |
| Headroom          | 45                  | Burst capacity + admin connections     |

> **Critical invariant:** No single client may exceed its allocated pool size.
> The headroom exists for healthy bursts, **not** to absorb a connection leak. If
> one client breaches its allocation and consumes the headroom, the primary hits
> `max_connections` and begins refusing new connections to *every* client —
> including `AuthLayer`, which then cannot validate tokens.

## Read Routing

Read-only queries (billing lookups, session checks) should target
`userdb-replica`. Routing reads to `userdb-primary` doubles the connection
pressure on the primary and is treated as a misconfiguration.

## Alerting

- `userdb_active_connections > 85` → warning
- `userdb_active_connections >= 100` → critical, pages Platform on-call
- `userdb_connection_refused_rate > 0` → critical
