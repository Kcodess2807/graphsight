# Service Dependencies & On-Call Runbook

This document captures the cross-service dependency graph, the blast radius of
each failure, and the standard runbook for the platform's highest-risk failure
mode: shared-database connection exhaustion.

## Dependency Matrix

| Service               | Hard dependencies                          | Repository            |
|-----------------------|--------------------------------------------|-----------------------|
| `APIGateway`          | `AuthLayer`                                | `api-gateway`         |
| `AuthLayer`           | `UserDB`                                    | `auth-layer`          |
| `PaymentService`      | `AuthLayer`, `UserDB`, PSP                  | `payment-service`     |
| `OrderService`        | `PaymentService`, `InventoryService`, `NotificationService` | `order-service` |
| `CartService`         | `InventoryService`                         | `cart-service`        |
| `InventoryService`    | —                                          | `inventory-service`   |
| `NotificationService` | —                                          | `notification-service`|
| `UserDB`              | — (it is a leaf datastore)                 | `user-db`             |

## Blast Radius: UserDB Exhaustion

Because `AuthLayer` and `PaymentService` share the `UserDB` primary, a connection
leak in `PaymentService` cascades as follows:

```
PaymentService leaks connections
        │
        ▼
UserDB primary hits max_connections (100)
        │
        ▼
AuthLayer cannot validate tokens (UserDB refuses connections)
        │
        ▼
APIGateway returns 401/503 for all authenticated routes
        │
        ▼
OrderService + CartService checkout flows fail
        │
        ▼
Client retries amplify load (thundering herd) → recovery delayed
```

## Runbook: "Checkout is down / auth failing platform-wide"

**Step 1 — Confirm the shared-DB signature.**
Check `userdb_active_connections`. If it is at or near 100 with a non-zero
`connection_refused_rate`, this is a `UserDB` exhaustion event, not an
`AuthLayer` bug, even though auth errors are the loudest symptom.

**Step 2 — Identify the offending client.**
Group active `UserDB` connections by client application. The service holding far
more than its allocation (`PaymentService` = 20, `AuthLayer` = 25) is the leaker.

**Step 3 — Check recent deploys.**
Look at the last deploys to `payment-service` and `auth-layer`. A connection
leak almost always traces to a change in pool config (`maximumPoolSize`,
`maxLifetime`, `connectionTimeout`) or a new synchronous `UserDB` call on the
authorization path.

**Step 4 — Mitigate.**
Roll back the offending deploy. Do **not** simply raise `max_connections` on the
primary — that masks the leak and risks OOM on `userdb-primary`.

**Step 5 — Drain the retry storm.**
After rollback, connection counts recover slowly because client retries keep
load high. Enable shed/back-pressure at `APIGateway` until pools normalize.

## Escalation

- Page order: Platform on-call → owning service's tech lead → Incident Commander.
- Declare SEV1 if checkout success rate drops below 90% for more than 5 minutes.
- Tech lead contacts: `PaymentService` → Alex Chen, `AuthLayer` → Priya Nair,
  `UserDB` → Jordan Lee, Checkout → Maria Rodriguez.
