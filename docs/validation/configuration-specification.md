# Configuration Specification (CS)

Generated 2026-10-05 from a freshly seeded database (`seed_baseline`). This is the *as-delivered* configuration; the site documents its own changes through change control.

## 1. Roles

| Role | Name | Admin role | Permissions |
|---|---|---|---|
| AUDITOR | Auditor / Read Only | no | 81 |
| DEPARTMENT_HEAD | Department Head | no | 23 |
| DISPATCH_USER | Dispatch User | no | 39 |
| MANAGEMENT | Management | no | 69 |
| PRODUCTION_MANAGER | Production Manager | no | 79 |
| PRODUCTION_USER | Production User | no | 69 |
| PURCHASE_MANAGER | Purchase Manager | no | 45 |
| PURCHASE_USER | Purchase User | no | 41 |
| QA_HEAD | QA Head | no | 180 |
| QA_OFFICER | QA Officer | no | 139 |
| QC_ANALYST | QC Analyst | no | 78 |
| QC_HEAD | QC Head | no | 90 |
| SYSTEM_ADMIN | System Administrator | yes | 49 |
| WAREHOUSE_USER | Warehouse User | no | 65 |

Permission catalogue: **256** permission codes across **36** modules.

## 2. Segregation-of-duties rules

| ID | Action | Conflicts with (same record) | Enforcement | Description |
|---|---|---|---|---|
| SOD-01 | `po.order.approve` | `po.order.create` | BLOCK | Creator of a PO cannot approve it |
| SOD-01b | `pr.request.approve` | `pr.request.create` | BLOCK | Creator of a PR cannot approve it |
| SOD-02 | `qc.result.review` | `qc.result.enter` | BLOCK | Analyst cannot review their own result |
| SOD-03 | `qa.lot.release` | `qc.result.review` | BLOCK | QC reviewer cannot also QA-release the lot |
| SOD-04 | `deviation.qa.approve` | `deviation.raise` | BLOCK | Deviation raiser cannot be sole QA approver |
| SOD-05 | `vendor.qualification.approve` | `vendor.qualification.author` | BLOCK | Qualification author cannot approve |
| SOD-06 | `conditional_release.approve` | `conditional_release.request` | BLOCK | Requester cannot approve |
| SOD-08 | `qc.amendment.approve` | `qc.amendment.request` | BLOCK | Requester cannot approve a result amendment |
| SOD-12 | `workflow.definition.approve` | `workflow.definition.author` | BLOCK | Workflow author cannot approve |
| SOD-13 | `vendor.approve` | `vendor.author` | BLOCK | Vendor record author cannot approve it |
| SOD-14 | `material.approve` | `material.author` | BLOCK | Material record author cannot approve it |
| SOD-15 | `spec.approve` | `spec.author` | BLOCK | Specification author cannot approve it |
| SOD-16 | `stp.approve` | `stp.author` | BLOCK | STP author cannot approve it |
| SOD-17 | `sampling_plan.approve` | `sampling_plan.author` | BLOCK | Sampling plan author cannot approve it |
| SOD-18 | `import.approve` | `import.submit` | BLOCK | Import submitter cannot approve the import |
| SOD-19 | `vendor_document.review` | `vendor_document.upload` | BLOCK | Uploader cannot review own vendor document |
| SOD-20 | `vendor_material.approve` | `vendor_material.author` | BLOCK | Mapping author cannot approve it |
| SOD-21 | `vendor_qualification.approve` | `vendor_qualification.author` | BLOCK | Qualification author cannot approve it |
| SOD-22 | `grn.receipt.verify` | `grn.receipt.create` | BLOCK | GRN must be verified by a second person |
| SOD-23 | `warehouse.destruction.approve` | `warehouse.destruction.request` | BLOCK | Destruction requester cannot approve |
| SOD-24 | `material.release.approve` | `qc.result.enter` | BLOCK | Analyst cannot review/release a lot they tested |
| SOD-25 | `bom.approve` | `bom.author` | BLOCK | BOM author cannot approve it |
| SOD-26 | `mfg.return.accept` | `mfg.return.request` | BLOCK | Return requester cannot accept it |
| SOD-27 | `mfg.step.verify` | `mfg.step.perform` | BLOCK | A second person verifies critical steps |
| SOD-28 | `mfg.reconciliation.qa_approve` | `mfg.reconciliation.production_approve` | BLOCK | QA approval of reconciliation by a different person |
| SOD-29 | `dispatch.order.approve` | `dispatch.order.create` | BLOCK | Dispatch creator cannot approve it |
| SOD-30 | `dispatch.order.dispatch` | `dispatch.order.approve` | BLOCK | Approver cannot also execute the dispatch |
| SOD-31 | `quality.deviation.close` | `quality.deviation.raise` | BLOCK | Deviation raiser cannot close it |
| SOD-32 | `quality.cc.approve` | `quality.cc.create` | BLOCK | Change requester cannot approve it |
| SOD-33 | `quality.risk.approve` | `quality.risk.author` | BLOCK | Risk assessment author cannot approve it |
| SOD-34 | `quality.capa.close` | `quality.capa.create` | BLOCK | CAPA creator cannot close it |
| SOD-35 | `sop.approve` | `sop.author` | BLOCK | SOP author cannot approve it |

## 3. Approval workflows (baseline)

**fg.release** — Finished goods release (QC to QA) (v1, APPROVED)

| Step | Name | Role | E-signature | Meaning | SLA h |
|---|---|---|---|---|---|
| 1 | QC Head review | QC_HEAD | yes | REVIEWED_BY | 48 |
| 2 | QA Officer verification | QA_OFFICER | yes | VERIFIED_BY | 48 |
| 3 | QA Head release | QA_HEAD | yes | QA_RELEASED | 48 |

**material.release** — Material release (QC to QA) (v1, APPROVED)

| Step | Name | Role | E-signature | Meaning | SLA h |
|---|---|---|---|---|---|
| 1 | QC Head review | QC_HEAD | yes | REVIEWED_BY | 48 |
| 2 | QA Officer verification | QA_OFFICER | yes | VERIFIED_BY | 48 |
| 3 | QA Head release | QA_HEAD | yes | QA_RELEASED | 48 |

**po.order** — Purchase order approval (v1, APPROVED)

| Step | Name | Role | E-signature | Meaning | SLA h |
|---|---|---|---|---|---|
| 1 | Purchase Manager approval | PURCHASE_MANAGER | yes | APPROVED_BY | 24 |

**pr.request** — Purchase request approval (v1, APPROVED)

| Step | Name | Role | E-signature | Meaning | SLA h |
|---|---|---|---|---|---|
| 1 | Department approval | DEPARTMENT_HEAD | no | REVIEWED_BY | 48 |
| 2 | Purchase review | PURCHASE_MANAGER | yes | APPROVED_BY | 48 |

## 4. Numbering registry

| Document type | Prefix | Reset | Format |
|---|---|---|---|
| ANIMAL | ANM | NEVER | `{prefix}-{seq:05d}` |
| ARCHIVE | ARC | YEARLY | `{prefix}-{year}-{seq:06d}` |
| BATCH_VOID | VOID | YEARLY | `{prefix}-{year}-{seq:06d}` |
| BLEED | BLD | NEVER | `{prefix}-{seq:05d}` |
| BOM | BOM | NEVER | `{prefix}-{seq:05d}` |
| CAPA | CAPA | YEARLY | `{prefix}-{year}-{seq:06d}` |
| CC | CC | YEARLY | `{prefix}-{year}-{seq:06d}` |
| COA | COA | YEARLY | `{prefix}-{year}-{seq:06d}` |
| COMPLAINT | CMP | YEARLY | `{prefix}-{year}-{seq:06d}` |
| CRELEASE | CRL | YEARLY | `{prefix}-{year}-{seq:06d}` |
| CUSTOMER | CUS | NEVER | `{prefix}-{seq:05d}` |
| DESTR | DES | YEARLY | `{prefix}-{year}-{seq:06d}` |
| DEVIATION | DEV | YEARLY | `{prefix}-{year}-{seq:06d}` |
| DISPATCH | DSP | YEARLY | `{prefix}-{year}-{seq:06d}` |
| EQUIPMENT | EQ | NEVER | `{prefix}-{seq:05d}` |
| FG | FG | YEARLY | `{prefix}-{year}-{seq:06d}` |
| GRN | GRN | YEARLY | `{prefix}-{year}-{seq:06d}` |
| HOLD | HLD | YEARLY | `{prefix}-{year}-{seq:06d}` |
| IMPORT | IMP | NEVER | `{prefix}-{seq:05d}` |
| INDENT | IND | YEARLY | `{prefix}-{year}-{seq:06d}` |
| ISSUE | ISS | YEARLY | `{prefix}-{year}-{seq:06d}` |
| LABEL | LBL | YEARLY | `{prefix}-{year}-{seq:06d}` |
| LOT | LOT | YEARLY | `{prefix}-{year}-{seq:06d}` |
| MATERIAL | MAT | NEVER | `{prefix}-{seq:05d}` |
| OOS | OOS | YEARLY | `{prefix}-{year}-{seq:06d}` |
| OOT | OOT | YEARLY | `{prefix}-{year}-{seq:06d}` |
| PO | PO | YEARLY | `{prefix}-{year}-{seq:06d}` |
| POOL | POOL | NEVER | `{prefix}-{seq:05d}` |
| PR | PR | YEARLY | `{prefix}-{year}-{seq:06d}` |
| QARELEASE | QAR | YEARLY | `{prefix}-{year}-{seq:06d}` |
| QCNO | QC | YEARLY | `{prefix}-{year}-{seq:06d}` |
| RECALL | RCL | YEARLY | `{prefix}-{year}-{seq:06d}` |
| RECON | REC | YEARLY | `{prefix}-{year}-{seq:06d}` |
| REPORTCOPY | RPT | YEARLY | `{prefix}-{year}-{seq:06d}` |
| RETURN | RTN | YEARLY | `{prefix}-{year}-{seq:06d}` |
| RISK | RA | YEARLY | `{prefix}-{year}-{seq:06d}` |
| SAMPLE | SMP | YEARLY | `{prefix}-{year}-{seq:06d}` |
| SFG | SFG | YEARLY | `{prefix}-{year}-{seq:06d}` |
| SOP | SOP | NEVER | `{prefix}-{seq:05d}` |
| SPEC | SPEC | NEVER | `{prefix}-{seq:05d}` |
| SPLAN | SPL | NEVER | `{prefix}-{seq:05d}` |
| STP | STP | NEVER | `{prefix}-{seq:05d}` |
| TEST | TST | YEARLY | `{prefix}-{year}-{seq:06d}` |
| VENDOR | VEN | NEVER | `{prefix}-{seq:05d}` |
| VQUAL | VQ | NEVER | `{prefix}-{seq:05d}` |

## 5. System configuration keys (defaults)

| Key | Default | Meaning |
|---|---|---|
| `backup.max_age_hours` | `26` | Alert when the newest successful backup record is older than this (hours) |
| `backup.restore_test_days` | `180` | Alert when the last restore test is older than this (days) |
| `calibration.override_allowed` | `false` | Allow QA-signed override of expired calibration |
| `cc.required_for_master_changes` | `false` | New versions of controlled masters need an approved change control (BR-CC-001) |
| `expiry.alert_days` | `90,60,30` | Expiry/retest alert thresholds (days) |
| `grn.over_delivery_tolerance_pct` | `0` | Allowed over-delivery % on GRN |
| `label.max_copies` | `10` | Maximum copies per label print |
| `loc.capacity_block` | `true` | Block put-away that exceeds location capacity |
| `po.over_delivery_tolerance_pct` | `0` | GRN over-delivery tolerance % |
| `po.required_docs.CRITICAL` | `GMP_CERTIFICATE,MANUFACTURING_LICENCE,QUALITY_AGREEMENT,COA_SAMPLE` | Vendor documents that must be approved and unexpired (critical vendors) |
| `po.required_docs.HIGH` | `GMP_CERTIFICATE,MANUFACTURING_LICENCE` | Required vendor documents (high risk) |
| `po.required_docs.LOW` | `` | Required vendor documents (low risk) |
| `po.required_docs.MEDIUM` | `MANUFACTURING_LICENCE` | Required vendor documents (medium risk) |
| `po.warn_vendor_due_days` | `60` | Warn on PO when vendor requalification is due within this many days |
| `recon.tolerance_pct` | `0.5` | Batch reconciliation tolerance % (unaccounted / issued) |
| `risk.rpn_high` | `200` | FMEA RPN at or above which a risk is HIGH |
| `risk.rpn_medium` | `100` | FMEA RPN at or above which a risk is MEDIUM |
| `stats.min_n_capability` | `25` | Minimum n for Cp/Cpk/Pp/Ppk |
| `training.gate` | `false` | Require valid training record before e-signing |
| `vq.alert_days` | `90,60,30,7` | Vendor requalification due-date alert thresholds (days) |
| `vq.default_validity_months` | `36` | Default requalification interval (months) suggested on a new qualification |

## 6. Retention policy defaults

| Record type | Years | Basis |
|---|---|---|
| Audit trail (`audit_trail`) | 10 | 21 CFR 11.10(e): at least as long as the underlying record |
| Electronic signatures (`e_signature`) | 10 | Linked to the signed record |
| Security events (`security_event`) | 3 | Site IT security policy |
| Inventory ledger (`inventory_transaction`) | 10 | EU GMP Ch.4: batch-related records |
| QC results (`qc_result`) | 10 | EU GMP Ch.6: at least 1 year after expiry / 5 years after certification |
| Certificates of analysis (`coa`) | 10 | EU GMP Ch.6 |
| Batch manufacturing records (`manufacturing_batch`) | 10 | EU GMP Ch.4.11: 1 year after expiry / 5 years after certification |
| Distribution records (`dispatch`) | 10 | EU GDP Ch.4 |
| Deviations (`deviation`) | 10 | EU GMP Ch.1 |
| CAPA (`capa`) | 10 | EU GMP Ch.1 |

## 7. Environment settings

See `docs/manuals/configuration.md` and `.env.example` (all `MERP_*` variables, secure defaults, production fail-fast checks).
