# Electronic Signature Specification (implemented in Phase 1)

* **Flow:** user submits meaning + reason + password → `esign.sign()` re-authenticates (local Argon2id or LDAP bind) **at every signing**; wrong password increments lockout counter → permission check (`required_permission`) → optional training gate (`training.gate`, per `training_code`) → canonical SHA-256 `record_hash` of the record snapshot → append-only `e_signature` row → audit entry (`E_SIGNATURE`, `signature_id`) → status transition links `signature_id` in `gmp_status_history`.
* **Manifestation (Part 11.50):** printed name, user ID, role(s), UTC timestamp, meaning, reason.
* **Linking (11.70):** `entity + record_id + record_version + record_hash + manifest_hash`; signed versions of versioned records are immutable, so a signature cannot be re-attached to different content.
* **Meanings:** CREATED_BY, REVIEWED_BY, APPROVED_BY, REJECTED_BY (reason mandatory), RELEASED_BY, SAMPLED_BY, TESTED_BY, VERIFIED_BY, QA_APPROVED, QA_RELEASED.
* **Controls:** unique users, no shared accounts (IDs never reused), SoD checks before signing, signatures append-only (ORM + DB trigger + DENY).
* **Site responsibilities:** written policy equating e-signatures to handwritten, identity verification at onboarding, FDA certification where applicable.
