# Access-Control Matrix

Role × module. Letters per module: the actions the role holds (full action names for non-obvious ones). The automated protocol `tests/security/test_access_matrix.py` verifies **every API route × every role** against the live permission catalogue (
298 permissions).

| Module | AUDITOR | COSTING_ANALYST | DEPARTMENT_HEAD | DISPATCH_USER | FINANCE_HEAD | MANAGEMENT | PRODUCTION_MANAGER | PRODUCTION_USER | PURCHASE_MANAGER | PURCHASE_USER | QA_HEAD | QA_OFFICER | QC_ANALYST | QC_HEAD | SYSTEM_ADMIN | WAREHOUSE_USER |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| antisera | R | R | — | — | R | R | C, R, U | C, R, U | — | — | R | R | R | R | — | — |
| audit | X, R | — | — | — | — | R | — | — | — | — | X, R, verify | X, R | — | — | X, R | — |
| backup | R | — | — | — | — | R | — | — | — | — | R, record | R | — | — | R, record | — |
| coa | R | — | — | R | — | R | R | R | — | — | generate, R | R | R | generate, R | — | — |
| conditional_release | R | — | — | — | — | R | R | R | — | — | A, C, R | C, R | R | R | — | — |
| config | R | — | — | — | — | — | — | — | — | — | R | R | — | — | R, run, U | — |
| costing | R | calculate, C, R, set, U | — | — | A, calculate, C, R, set, U | R | — | — | — | — | — | — | — | — | — | — |
| dashboard | R | R | R | R | R | R | R | R | R | R | R | R | R | R | R | R |
| dispatch | R | — | — | cancel, C, deliver, dispatch, X, R, U, validate | — | R | — | — | — | — | A, X, R | A, X, R | R | R | — | — |
| doc | R | R | R | R | R | R | R | R | C, R | C, R | C, R | C, R | C, R | C, R | — | R |
| em | R | — | — | — | — | R | — | C, R | — | — | A, C, R, review, U | C, R, review, U | C, enter, R | C, enter, R, U | — | — |
| esign | R | — | — | — | — | — | — | — | — | — | R | R | — | — | — | — |
| grn | X, R | X, R | — | — | X, R | X, R | R | R | — | R | exception, X, R, reject | X, R, reject | R | R | — | cancel, C, X, R, S, U, verify |
| iam | R | — | — | — | — | — | — | — | — | — | R | R | — | — | assign_role, C, deactivate, R, reset_password, revoke, U | — |
| import | R | — | — | — | — | — | — | — | A, C, R | C, R | A, C, R | C, R | C, R | C, R | — | — |
| inventory | X, R | X, R | — | R | X, R | X, R | R | R | — | — | X, R, verify | X, R | R | R | — | X, R, transfer |
| label | — | — | — | — | — | — | print | print | — | — | print | print | print | print | — | print |
| md | X, R | X, R | X, R | C, X, R, U | X, R | X, R | C, X, R, U | C, X, R, U | A, C, deactivate, X, R, U | C, X, R, U | A, C, deactivate, X, R, review_document, U | C, X, R, review_document, U | C, X, R, U | C, X, R, U | C, X, R, U | C, X, R, U |
| mfg | R | R | — | R | R | R | additional, A, cancel, C, execute, R, record, request, U, use, verify | C, execute, R, record, request, U, use | — | — | override_number, qa_approve, R, release_check | R, release_check | R | R | — | accept, C, R |
| notification | R | R | R | R | R | R | R | R | R | R | R | R | R | R | R | R |
| oos | R | — | — | — | — | R | R | R | — | — | decide, R, U | R, U | C, R, U | C, R, U | — | — |
| oot | R | — | — | — | — | R | R | R | — | — | R, review | R, review | R | R, review | — | — |
| org | R | — | — | — | — | — | — | — | — | — | R | R | — | — | C, R, U | — |
| po | X, R | — | — | — | — | X, R | — | — | A, cancel, C, X, R, S, U | cancel, C, X, R, S, U | X, R | X, R | — | — | — | — |
| pr | X, R | — | A, cancel, C, R, S, U | — | — | X, R | cancel, C, R, S, U | cancel, C, R, S, U | A, cancel, C, X, R, S, U | cancel, C, X, R, S, U | cancel, C, X, R, S, U | cancel, C, X, R, S, U | cancel, C, R, S, U | cancel, C, R, S, U | — | cancel, C, R, S, U |
| qa | R | R | — | — | R | R | R | R | — | — | place, R, reject, Rel | place, R | R | R | — | R |
| qc | R | — | — | — | — | R | R | R | — | — | A, dispose, override_calibration, R | A, R | amend_request, C, enter, R, start, S | amend_approve, amend_request, A, assign, C, enter, R, start, S | — | — |
| quality | acknowledge, R | — | — | acknowledge, C, R | — | acknowledge, R | acknowledge, C, investigate, R, U | acknowledge, C, R, U | — | — | acknowledge, A, assess, cancel, close, C, investigate, R, U | acknowledge, assess, cancel, C, investigate, R, U | acknowledge, C, R, U | acknowledge, C, investigate, R, U | — | acknowledge, C, R, U |
| reports | R, run | R, run | — | R, run | R, run | R, run | R, run | R, run | R, run | R, run | R, run | R, run | R, run | R, run | R | R, run |
| retention | R | — | — | — | — | R | — | — | — | — | C, R, U | R | — | — | R | — |
| security | R | — | — | — | — | — | — | — | — | — | R | R | — | — | R | — |
| stability | R | — | — | — | — | R | — | — | — | — | A, conclude, C, R, review, skip, start, terminate, U | C, R, review, skip, U | enter, R, record | C, enter, R, record, skip, start, terminate, U | — | — |
| stats | R | — | — | — | — | R | R | R | — | — | R | R | R | R | — | — |
| trace | R | — | — | R | — | R | — | — | — | — | R | R | R | R | — | — |
| training | R | — | — | — | — | — | — | — | — | — | R | R | — | — | C, R | — |
| vm | R | — | — | — | — | R | — | — | C, R, U | C, R, U | A, C, R, U, withdraw | C, R, U | — | — | — | — |
| vq | R | — | — | — | — | R | — | — | R | R | A, C, disqualify, R, suspend, U | C, R, U | — | — | — | — |
| warehouse | R | R | — | — | R | R | — | — | — | — | A, R, U | R | — | — | — | C, R |
| workflow | R | — | — | — | — | — | R | — | — | — | A, R | R | — | R | C, R, U | — |
