# Security Policy

## Supported version

Security fixes are applied to the default branch. This research prototype does
not yet promise long-term support for older tags.

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting feature for this
repository. Do not open a public issue containing credentials, unpublished
manuscripts, private datasets, or exploit details.

Include the affected path or endpoint, reproduction steps, impact, and any
suggested mitigation. You should receive an acknowledgment within seven days.

## Deployment note

Local development mode can use permissive settings. Before exposing an
instance, configure authentication, secrets, storage, logging, rate limits, and
model-provider data handling for the deployment environment. Never commit a
populated `.env` file.

## ChromaDB deployment boundary

The project uses ChromaDB only through local `PersistentClient` and
`EphemeralClient` instances. Do not run or expose Chroma's HTTP server,
including its `/api/v2` routes.

As of 2026-07-12, upstream advisory
`GHSA-f4j7-r4q5-qw2c` / `CVE-2026-45829` affects every available ChromaDB
1.x release and has no upstream patch. BioTeam-AI therefore temporarily pins
ChromaDB 0.6.3, outside the reported vulnerable range, in addition to keeping
the server surface disabled.

ChromaDB 1.x persistence files are not compatible with this temporary pin.
Before moving an existing local checkout from v0.1.0 to v0.1.1, archive or
remove `data/chroma/`; BioTeam-AI will create a fresh embedded store. No
Chroma persistence data are tracked in this repository.
