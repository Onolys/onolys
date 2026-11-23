---
assurance:
  id: t-2
  base: sha256:d4f646a79ea4490dc0bb16d995b4eeb2b531f6e2897c13416a93bc882c39bec1
---
# Non-allowlisted account receives 403 and cannot reach New run

> A signed-in account absent from the allowed-email list receives HTTP 403 from public evaluation API access and sees Not allowed rather than New run.

## Step 1 @verifies ac-5, ac-6

Open {{eval_site_url}}, set localStorage key {{forbidden_storage_key}} to the exact value {{forbidden_storage_value}} from the official Firebase SDK authenticated disposable user session, reload the page, then assert "Not allowed" is shown and the New run screen is not accessible to this account. Do not display or extract the secret storage values. This setup uses normal SDK session persistence and does not test email/password provider sign-in.

## Step 2 @verifies ac-4

Reload the evaluation site while keeping the authenticated disposable user session, then verify the browser request to /v1/me returns HTTP status 403 and "Not allowed" remains visible. Observe the page network request without extracting or printing credentials.
