import fc from "fast-check";

// endOnFailure=false retains shrinking; fast-check reports seed and replay path.
fc.configureGlobal({ seed: 20261124, numRuns: 5000 });
