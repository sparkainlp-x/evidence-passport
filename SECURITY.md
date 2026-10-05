# Security Policy

Please report potential vulnerabilities privately to the repository owner rather than opening a public issue. Include a minimal reproduction, the affected commit, and the impact.

Evidence Passport is an offline, standard-library-only CLI: it makes no network requests and starts no server by design. Any change that introduces a network call, remote asset load, or path escape outside the manifest directory is in scope. A case where a SHA-256 mismatch is accepted, or where a path traversal is not rejected, is in scope.
