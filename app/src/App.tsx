import { useEffect, useState } from 'react';
import { ServiceSelector, type Svc } from './ServiceSelector';
import { CredentialForm } from './CredentialForm';
import { BookList } from './BookList';
import { DownloadProgress } from './DownloadProgress';
import { SettingsPanel } from './SettingsPanel';
import { Onboarding } from './Onboarding';
import { DownloadedList } from './DownloadedList';
import { itError } from './errors';
import type { Book } from './types';

const devApi = 'http://127.0.0.1:8923';

async function resolveApi() {
  if (!('__TAURI_INTERNALS__' in window)) return devApi;
  try {
    const { invoke } = await import('@tauri-apps/api/core');
    return `http://127.0.0.1:${await invoke<number>('sidecar_port')}`;
  } catch {
    return devApi;
  }
}

async function getJsonWhenReady(url: string) {
  for (let attempt = 0; attempt < 24; attempt++) {
    try {
      const response = await fetch(url);
      if (response.ok) return await response.json();
    } catch { /* il sidecar può essere ancora in avvio */ }
    await new Promise(resolve => setTimeout(resolve, 250));
  }
  throw new Error('sidecar unavailable');
}

export default function App() {
  const [api, setApi] = useState('');
  const [services, setServices] = useState<Svc[]>([]);
  const [service, setService] = useState('');
  const [user, setUser] = useState('');
  const [pass, setPass] = useState('');
  const [books, setBooks] = useState<Book[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [isbn, setIsbn] = useState('');
  const [jobIds, setJobIds] = useState<string[]>([]);
  const [doneTick, setDoneTick] = useState(0);
  const [msg, setMsg] = useState('Scegli un servizio per iniziare.');
  const [loggedIn, setLoggedIn] = useState(false);
  const [loginBusy, setLoginBusy] = useState(false);
  const [outputPath, setOutputPath] = useState('');
  const [savingPath, setSavingPath] = useState(false);
  const [, force] = useState(0);
  const [hasSaved, setHasSaved] = useState(false);
  const [useSaved, setUseSaved] = useState(false);
  const [cookie, setCookie] = useState('');

  const svc = services.find(s => s.id === service);
  const activeCount = services.filter(s => s.implemented).length;

  useEffect(() => { resolveApi().then(setApi); }, []);

  useEffect(() => {
    if (!api) return;
    getJsonWhenReady(`${api}/services`).then(async d => {
      const list: Svc[] = d.services ?? [];
      setServices(list);
      let last = '';
      try { last = (await fetch(`${api}/last-service`).then(r => r.json())).service ?? ''; } catch { /* offline */ }
      if (!last) last = localStorage.getItem('bd-last-service') ?? '';
      const fallback = list.find(s => s.implemented)?.id ?? '';
      setService(last && list.some(s => s.id === last && s.implemented) ? last : fallback);
    }).catch(() => setMsg(itError('fetch failed')));
    fetch(`${api}/settings/output-directory`).then(r => r.json()).then(d => setOutputPath(d.path ?? '')).catch(() => {});
  }, [api]);

  useEffect(() => {
    if (!api || !service) return;
    localStorage.setItem('bd-last-service', service);
    setBooks([]); setSelected([]); setJobIds([]); setLoggedIn(false);
    setPass(''); setUseSaved(false); setHasSaved(false);
    fetch(`${api}/account?service=${service}`).then(r => r.json()).then(a => {
      setUser(a.username ?? '');
      setHasSaved(!!a.hasPassword);
      setUseSaved(!!a.hasPassword);
    }).catch(() => {});
  }, [api, service]);

  async function login() {
    if (!svc?.implemented) return;
    setMsg('Accesso in corso…');
    setLoginBusy(true);
    try {
      const r = await fetch(`${api}/login`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ service, username: user, password: useSaved ? '' : pass, use_saved_password: useSaved, session_cookie: cookie }),
      });
      const d = await r.json();
      if (!r.ok) { setMsg(itError(d.detail, r.status)); setLoggedIn(false); return; }
      setHasSaved(true); setLoggedIn(true);
      setMsg(d.listWarning ? `Accesso riuscito, ma lista non caricata: ${d.listWarning}` : `${d.books?.length ?? 0} libri trovati.`);
      setBooks(d.books ?? []); setSelected([]); setDoneTick(x => x + 1);
    } catch { setMsg(itError('fetch failed')); }
    finally { setLoginBusy(false); }
  }

  function toggle(id: string) {
    setSelected(s => s.includes(id) ? s.filter(x => x !== id) : [...s, id]);
  }

  function toggleAll(ids: string[]) {
    setSelected(s => ids.every(id => s.includes(id)) ? s.filter(id => !ids.includes(id)) : [...new Set([...s, ...ids])]);
  }

  async function startDownload(url: string, body: object, message: string) {
    const r = await fetch(`${api}${url}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    });
    const d = await r.json();
    if (!r.ok) { setMsg(itError(d.detail, r.status)); return; }
    setJobIds(d.jobIds ?? [d.jobId]); setMsg(message);
  }

  async function chooseOutputDirectory() {
    if ('__TAURI_INTERNALS__' in window) {
      try {
        const { open } = await import('@tauri-apps/plugin-dialog');
        const chosen = await open({ directory: true, multiple: false, title: 'Scegli dove salvare i libri' });
        if (typeof chosen === 'string') await saveOutputDirectory(chosen);
        return;
      } catch { /* usa il dialogo nativo del sidecar */ }
    }
    try {
      const r = await fetch(`${api}/settings/choose-output-directory`, { method: 'POST' });
      const d = await r.json();
      if (!r.ok) { setMsg(d.detail ?? 'Impossibile aprire il selettore cartella.'); return; }
      if (d.path) { setOutputPath(d.path); setDoneTick(x => x + 1); setMsg('Cartella di destinazione aggiornata.'); }
    } catch { setMsg(itError('fetch failed')); }
  }

  async function saveOutputDirectory(path = outputPath) {
    setSavingPath(true);
    try {
      const r = await fetch(`${api}/settings/output-directory`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path }),
      });
      const d = await r.json();
      if (!r.ok) { setMsg(d.detail ?? 'Cartella non valida.'); return; }
      setOutputPath(d.path); setDoneTick(x => x + 1); setMsg('Cartella di destinazione aggiornata.');
    } catch { setMsg(itError('fetch failed')); }
    finally { setSavingPath(false); }
  }

  return (
    <div className="app-shell">
      <aside className="service-rail">
        <div className="brand"><span className="brand-mark" aria-hidden="true">BD</span><div><strong>Book Downloader</strong><small>La tua libreria, in ordine.</small></div></div>
        <ServiceSelector items={services} value={service} onPick={setService} />
        <div className="rail-summary"><strong>{activeCount}</strong><span>servizi pronti</span><small>{services.length - activeCount} integrazioni pianificate</small></div>
      </aside>

      <main className="workspace">
        <header className="workspace-header">
          <div><span className="eyebrow">Biblioteca digitale</span><h1>I miei libri</h1><p>{svc?.description ?? 'Collega un servizio e raccogli qui i tuoi libri.'}</p></div>
          <section className="destination" aria-labelledby="destination-title">
            <div><span className="section-kicker">Destinazione</span><strong id="destination-title">Dove salvo i download</strong></div>
            <div className="path-row">
              <input id="output-path" value={outputPath} onChange={e => setOutputPath(e.target.value)} aria-label="Cartella di destinazione" />
              <button className="button secondary" onClick={chooseOutputDirectory}>Scegli cartella</button>
              <button className="button text-button" onClick={() => saveOutputDirectory()} disabled={!outputPath || savingPath}>{savingPath ? 'Salvo…' : 'Salva'}</button>
            </div>
          </section>
        </header>

        <Onboarding onClose={() => force(x => x + 1)} />
        {msg && <div className="notice" role="status"><span className="notice-dot" aria-hidden="true" />{msg}</div>}

        <div className="content-grid">
          <div className="primary-column">
            <section className="panel login-panel">
              <div className="panel-heading"><div><span className="section-kicker">01 · Accesso</span><h2>{svc?.label ?? 'Servizio'}</h2></div><span className={`status-pill ${loggedIn ? 'connected' : ''}`}>{loggedIn ? 'Collegato' : 'Non collegato'}</span></div>
              <CredentialForm user={user} pass={pass} setUser={setUser} setPass={setPass} onLogin={login}
                hasSaved={hasSaved} useSaved={useSaved} setUseSaved={setUseSaved} busy={loginBusy}
                usernameLabel={svc?.usernameLabel ?? 'Nome utente'} loginHint={svc?.loginHint ?? ''}
                showCookie={service === 'bsmart'} cookie={cookie} setCookie={setCookie} />
            </section>

            <BookList books={books} selected={selected} loggedIn={loggedIn} onToggle={toggle} onToggleAll={toggleAll}
              onDl={() => startDownload('/download-all', { service, book_ids: selected }, `Download avviato per ${selected.length} libri…`)} />

            {service === 'zanichelli-booktab' && loggedIn && (
              <section className="panel isbn-panel"><div><span className="section-kicker">Libro assente?</span><h2>Scarica con ISBN digitale</h2><p>Usa l’ISBN dell’eBook, non quello del volume cartaceo.</p></div><div className="isbn-row"><input value={isbn} onChange={e => setIsbn(e.target.value)} placeholder="9788808298003" inputMode="numeric" aria-label="ISBN digitale" /><button className="button secondary" onClick={() => startDownload('/download', { service, book_id: isbn.trim() }, `Download ISBN ${isbn.trim()} avviato…`)} disabled={!isbn.trim()}>Scarica</button></div></section>
            )}
          </div>

          <aside className="activity-column">
            <DownloadProgress jobIds={jobIds} api={api} onDone={() => { setDoneTick(x => x + 1); setMsg('Download completati.'); }} />
            <DownloadedList api={api} tick={doneTick} />
            <SettingsPanel api={api} service={service} onBooks={items => { setBooks(items); setSelected([]); setLoggedIn(true); setDoneTick(x => x + 1); }} onForgot={() => { setUser(''); setPass(''); setHasSaved(false); setUseSaved(false); setBooks([]); setLoggedIn(false); }} />
          </aside>
        </div>
      </main>
    </div>
  );
}
