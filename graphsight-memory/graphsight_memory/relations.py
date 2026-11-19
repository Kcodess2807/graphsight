"""The relations an agent may store, each read as SUBJECT RELATION OBJECT.

A closed list stops the drift where one fact is stored as OWNED_BY and its update
as OWNER, so the update never replaces it. Pass relations=None to Memory to allow
any name.
"""

RELATIONS: dict[str, str] = {
    "OWNED_BY": "src/checkout.py OWNED_BY payments team",
    "MAINTAINED_BY": "docs site MAINTAINED_BY docs team",
    "ASSIGNED_TO": "Issue #12 ASSIGNED_TO alice",
    "CONTACT": "Issue #12 CONTACT bob",
    "REVIEWER": "src/auth.py REVIEWER carol",
    "APPROVER": "release.yml APPROVER dave",
    "MEMBER_OF": "alice MEMBER_OF platform team",
    "WORKS_FROM": "alice WORKS_FROM Lisbon office",
    "BLOCKED_BY": "PR #40 BLOCKED_BY Issue #12",
    "DEPENDS_ON": "checkout-service DEPENDS_ON stripe-sdk",
    "DUPLICATE_OF": "Issue #13 DUPLICATE_OF Issue #12",
    "TRACKED_IN": "Issue #12 TRACKED_IN QA-88",
    "HOSTED_ON": "CI dashboard HOSTED_ON Datadog",
    "DEPLOYED_TO": "checkout-service DEPLOYED_TO eu-west-1",
    "PUBLISHED_FROM": "release builds PUBLISHED_FROM GitHub Actions",
    "SCHEDULED_FOR": "v2.0 SCHEDULED_FOR April",
    "RELEASE_MANAGER": "v2.0 RELEASE_MANAGER erin",
    "DECIDED": "platform team DECIDED drop Python 3.9",
}
