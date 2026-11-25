# TEMPORARY (PRD 03-eval-environment R6a): the secret shell `eval-allowed-emails-eval` was created out of band
# (same automatic replication as the module shells) and already holds the copied allowlist. The block below adopts it
# on the owner's first apply instead of failing with 409. Its target is the module's eval_allowed_emails secret (eval_backend_enabled = true).
# Delete this file in a follow-up commit after the first apply.
#
import {
  to = module.eval.google_secret_manager_secret.eval_allowed_emails[0]
  id = "projects/onolys/secrets/eval-allowed-emails-eval"
}
