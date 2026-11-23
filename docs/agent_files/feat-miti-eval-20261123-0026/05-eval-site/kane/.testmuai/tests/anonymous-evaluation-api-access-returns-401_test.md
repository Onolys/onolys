---
assurance:
  id: t-1
  base: sha256:9d59797eeea603a99813f0b41e8d361da40203bef7f1b8b2dcd701ae3f05391a
---
# Anonymous evaluation API access returns 401

> An anonymous request to the public evaluation API /v1/me receives HTTP 401.

## Step 1

Open {{eval_site_url}} in a fresh anonymous browser session, then verify the Sign in form is visible with email, password and Sign in with Google controls.

## Step 2 @verifies ac-3

From the browser, request GET {{eval_api_url}}/v1/me without any Authorization token, then assert the HTTP response status is 401.
