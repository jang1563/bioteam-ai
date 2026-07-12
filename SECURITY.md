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
