import { useState } from 'react';
import type { Book } from './types';

export function SettingsPanel({ api, service, onBooks, onForgot }: {
  api: string; service: string; onBooks: (books: Book[]) => void; onForgot: () => void;
}) {
  const [msg, setMsg] = useState('');
  async function reload() {
    const r = await fetch(`${api}/books?service=${service}`);
    const d = await r.json();
    setMsg(r.ok ? 'Libreria aggiornata.' : (d.detail ?? 'Devi prima accedere.'));
    if (r.ok) onBooks(d.books ?? []);
  }
  async function forget() {
    if (!service || !confirm('Dimenticare le credenziali salvate per questo servizio?')) return;
    const r = await fetch(`${api}/account?service=${service}`, { method: 'DELETE' });
    setMsg(r.ok ? 'Credenziali rimosse.' : 'Operazione non riuscita.');
    if (r.ok) onForgot();
  }
  return <details className="side-panel settings-panel"><summary>Gestione account</summary><div className="settings-actions"><button className="button secondary" onClick={reload}>Ricarica libreria</button><button className="button danger" onClick={forget}>Dimentica credenziali</button></div>{msg && <p className="muted">{msg}</p>}</details>;
}
