# TEMPORARY (PRD 03-eval-environment R6a): the secret shell `eval-allowed-emails-eval` was created out of band
# (same automatic replication as the module shells) and already holds the copied allowlist. The block below adopts it
# on the owner's first apply instead of failing with 409. It is commented out only because its target resource
# (module "eval" + the module's eval_allowed_emails secret, Task 6) does not exist yet; Task 6 must uncomment it
# together with that resource, and the block is deleted in a follow-up commit after the first apply.
#
# import {
#   to = module.eval.google_secret_manager_secret.eval_allowed_emails[0]
#   id = "projects/onolys/secrets/eval-allowed-emails-eval"
# }
