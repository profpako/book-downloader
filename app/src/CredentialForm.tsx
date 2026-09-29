import { useState } from 'react';

export function CredentialForm({ user, pass, setUser, setPass, onLogin, hasSaved, useSaved, setUseSaved, busy, usernameLabel, loginHint, showCookie, cookie, setCookie }: {
  user: string; pass: string; setUser: (v: string) => void; setPass: (v: string) => void;
  onLogin: () => void; hasSaved: boolean; useSaved: boolean; setUseSaved: (v: boolean) => void; busy: boolean;
  usernameLabel: string; loginHint: string; showCookie: boolean; cookie: string; setCookie: (v: string) => void;
}) {
  const [show, setShow] = useState(false);
  return (
    <form className="credential-form" onSubmit={e => { e.preventDefault(); onLogin(); }}>
      <label><span>{usernameLabel || 'Nome utente'}</span><input value={user} onChange={e => { setUser(e.target.value); setUseSaved(false); }} autoComplete="username" placeholder={usernameLabel === 'Email' ? 'nome@esempio.it' : ''} /></label>
      {!useSaved && <label><span>Password</span><div className="password-field"><input type={show ? 'text' : 'password'} value={pass} onChange={e => setPass(e.target.value)} autoComplete="current-password" /><button type="button" onClick={() => setShow(s => !s)}>{show ? 'Nascondi' : 'Mostra'}</button></div></label>}
      {hasSaved && <label className="saved-password"><input type="checkbox" checked={useSaved} onChange={e => setUseSaved(e.target.checked)} /><span>Usa la password salvata{user ? ` per ${user}` : ''}</span></label>}
      {loginHint && <p className="field-note">{loginHint}</p>}
      <button className="button primary" type="submit" disabled={busy}>{busy ? 'Accesso…' : 'Accedi e carica i libri'}</button>
      {showCookie && <details className="cookie-access"><summary>Accesso Google o Microsoft</summary><p>Incolla il valore del cookie <code>_bsw_session_v1_production</code>.</p><label><span>Cookie sessione</span><input value={cookie} onChange={e => setCookie(e.target.value)} autoComplete="off" /></label><button className="button secondary" type="button" onClick={onLogin}>Accedi con cookie</button></details>}
    </form>
  );
}
