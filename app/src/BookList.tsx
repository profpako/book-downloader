import { useState } from 'react';
import type { Book } from './types';

export function BookList({ books, selected, loggedIn, onToggle, onToggleAll, onDl }: {
  books: Book[]; selected: string[]; loggedIn: boolean;
  onToggle: (id: string) => void; onToggleAll: (ids: string[]) => void; onDl: () => void;
}) {
  const [query, setQuery] = useState('');
  const shown = books.filter(b => b.title.toLowerCase().includes(query.trim().toLowerCase()));
  const shownIds = shown.map(b => b.id);
  const allShown = shown.length > 0 && shownIds.every(id => selected.includes(id));
  return (
    <section className="panel library-panel">
      <div className="panel-heading"><div><span className="section-kicker">02 · Libreria</span><h2>{loggedIn ? `${books.length} libri` : 'I tuoi libri'}</h2></div>{loggedIn && books.length > 0 && <input className="book-search" type="search" value={query} onChange={e => setQuery(e.target.value)} placeholder="Cerca un titolo" aria-label="Cerca un libro" />}</div>
      {!loggedIn ? <div className="empty-state"><strong>La libreria apparirà qui.</strong><p>Accedi al servizio selezionato per caricare i titoli associati al tuo account.</p></div>
        : !books.length ? <div className="empty-state"><strong>Nessun libro restituito.</strong><p>L’accesso è riuscito, ma questo servizio non ha restituito titoli.</p></div>
        : <>
          <div className="selection-bar"><label><input type="checkbox" checked={allShown} onChange={() => onToggleAll(shownIds)} /> Seleziona {query ? 'i risultati' : 'tutti'}</label><span>{selected.length} selezionati</span></div>
          <ul className="book-list">{shown.map((b, index) => {
            const details = [b.author, b.publisher, b.isbn && `ISBN ${b.isbn}`].filter(Boolean);
            return <li key={b.id}><label title={`ID ${b.id}`}><input type="checkbox" checked={selected.includes(b.id)} onChange={() => onToggle(b.id)} /><span className="book-number">{String(index + 1).padStart(2, '0')}</span><span className="book-copy"><strong>{b.title}</strong>{b.subtitle && <span>{b.subtitle}</span>}{details.length > 0 && <small>{details.join(' · ')}</small>}</span></label></li>;
          })}</ul>
          {!shown.length && <div className="empty-state compact"><strong>Nessun titolo corrisponde alla ricerca.</strong></div>}
          <div className="library-actions"><button className="button primary" onClick={onDl} disabled={!selected.length}>Scarica {selected.length ? `${selected.length} ${selected.length === 1 ? 'libro' : 'libri'}` : 'selezione'}</button></div>
        </>}
    </section>
  );
}
