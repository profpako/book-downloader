import { useEffect, useState } from 'react';

type DownloadedBook = {
  name: string; path: string; title: string; subtitle?: string; author?: string;
  publisher?: string; isbn?: string; service?: string; bookId?: string; size?: number;
};

const serviceNames: Record<string, string> = {
  'zanichelli-booktab': 'Zanichelli', hubscuola: 'HUB Scuola', bsmart: 'bSmart',
};

function sizeLabel(bytes = 0) {
  return bytes ? `${(bytes / 1024 / 1024).toFixed(1)} MB` : '';
}

export function DownloadedList({ api, tick }: { api: string; tick: number }) {
  const [files, setFiles] = useState<DownloadedBook[]>([]);
  const [dir, setDir] = useState('');
  const [deleting, setDeleting] = useState('');
  const [error, setError] = useState('');
  useEffect(() => {
    if (api) fetch(`${api}/downloads`).then(r => r.json()).then(d => { setFiles(d.files ?? []); setDir(d.dir ?? ''); }).catch(() => {});
  }, [api, tick]);

  async function remove(file: DownloadedBook) {
    if (!window.confirm(`Eliminare definitivamente “${file.title || file.name}”?`)) return;
    setDeleting(file.name);
    setError('');
    try {
      const response = await fetch(`${api}/downloads/${encodeURIComponent(file.name)}`, { method: 'DELETE' });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Eliminazione non riuscita.');
      setFiles(current => current.filter(item => item.name !== file.name));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Eliminazione non riuscita.');
    } finally {
      setDeleting('');
    }
  }

  return (
    <section className="side-panel downloads-panel">
      <div className="panel-heading compact"><div><span className="section-kicker">Archivio locale</span><h2>Scaricati</h2></div><span className="count-badge">{files.length}</span></div>
      {dir && <p className="archive-path" title={dir}>{dir}</p>}
      {error && <p className="archive-error" role="alert">{error}</p>}
      {!files.length ? <p className="muted">Nessun PDF in questa cartella.</p> : <ul className="download-list">{files.slice().reverse().map(f => {
        const details = [serviceNames[f.service ?? ''] ?? f.service, f.publisher, f.isbn && `ISBN ${f.isbn}`, sizeLabel(f.size)].filter(Boolean);
        return <li key={f.path} title={`File: ${f.name}`}><span className="file-mark" aria-hidden="true">PDF</span><span className="download-info"><strong>{f.title || f.name}</strong>{f.subtitle && <span>{f.subtitle}</span>}{f.author && <span className="book-author">{f.author}</span>}<small>{details.join(' · ')}</small><code>{f.name}</code></span><button type="button" className="delete-download" onClick={() => remove(f)} disabled={deleting === f.name} aria-label={`Elimina ${f.title || f.name}`}>{deleting === f.name ? '…' : 'Elimina'}</button></li>;
      })}</ul>}
    </section>
  );
}
