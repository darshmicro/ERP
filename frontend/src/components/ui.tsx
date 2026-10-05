import { ReactNode, useState } from "react";

const STATUS_CLASS: Record<string, string> = {
  DRAFT: "secondary", PENDING: "warning", APPROVED: "success", REJECTED: "danger", QUARANTINE: "warning",
  RELEASED: "success", EXPIRED: "dark", HOLD: "danger", SUPERSEDED: "secondary", IN_PROGRESS: "info",
  ACTIVE: "success", INACTIVE: "secondary", LOCKED: "danger",
};
export const StatusBadge = ({ status }: { status: string }) => (
  <span className={`badge text-bg-${STATUS_CLASS[status] ?? "secondary"}`}>{status}</span>
);

export const Alert = ({ kind = "danger", children }: { kind?: string; children: ReactNode }) =>
  children ? <div className={`alert alert-${kind} py-2`} role="alert">{children}</div> : null;

export function Modal({ title, onClose, children, footer }: { title: string; onClose: () => void; children: ReactNode; footer?: ReactNode }) {
  return (
    <>
      <div className="modal d-block" tabIndex={-1} role="dialog">
        <div className="modal-dialog"><div className="modal-content">
          <div className="modal-header"><h5 className="modal-title">{title}</h5><button className="btn-close" onClick={onClose} aria-label="Close" /></div>
          <div className="modal-body">{children}</div>
          {footer && <div className="modal-footer">{footer}</div>}
        </div></div>
      </div>
      <div className="modal-backdrop show" />
    </>
  );
}

/** Reason prompt used for every GMP-relevant change (sent as X-Change-Reason). */
export function ReasonDialog({ title, onSubmit, onClose, needPassword = false, meaning }: {
  title: string; onSubmit: (reason: string, password: string) => Promise<void>; onClose: () => void; needPassword?: boolean; meaning?: string;
}) {
  const [reason, setReason] = useState(""); const [pw, setPw] = useState(""); const [err, setErr] = useState(""); const [busy, setBusy] = useState(false);
  const go = async () => {
    setBusy(true); setErr("");
    try { await onSubmit(reason, pw); onClose(); } catch (e: any) { setErr(e.message); setBusy(false); }
  };
  return (
    <Modal title={title} onClose={onClose} footer={<>
      <button className="btn btn-outline-secondary" onClick={onClose}>Cancel</button>
      <button className="btn btn-primary" disabled={busy || !reason.trim() || (needPassword && !pw)} onClick={go}>
        {needPassword ? "Sign & confirm" : "Confirm"}</button></>}>
      <Alert>{err}</Alert>
      {needPassword && <p className="small text-muted">Electronic signature{meaning ? ` — meaning: ${meaning}` : ""}. Re-enter your password to sign.</p>}
      <label className="form-label">Reason / comment <span className="text-danger">*</span></label>
      <textarea className="form-control mb-2" rows={2} value={reason} onChange={(e) => setReason(e.target.value)} />
      {needPassword && <><label className="form-label">Password</label>
        <input type="password" autoComplete="current-password" className="form-control" value={pw} onChange={(e) => setPw(e.target.value)} /></>}
    </Modal>
  );
}

export const PageHeader = ({ title, crumbs, actions }: { title: string; crumbs?: string[]; actions?: ReactNode }) => (
  <div className="d-flex justify-content-between align-items-end mb-3 border-bottom pb-2">
    <div>
      {crumbs && <nav className="small text-muted">{crumbs.join(" › ")}</nav>}
      <h4 className="mb-0">{title}</h4>
    </div>
    <div className="d-flex gap-2">{actions}</div>
  </div>
);

export const fmt = (iso?: string | null) => (iso ? new Date(iso).toLocaleString(undefined, { hour12: false, timeZoneName: "short" }) : "—");
