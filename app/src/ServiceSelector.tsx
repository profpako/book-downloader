export type Svc = {
  id: string; label: string; implemented: boolean; description?: string;
  needsBrowser?: boolean; usernameLabel?: string; loginHint?: string;
};

export function ServiceSelector({ items, value, onPick }: { items: Svc[]; value: string; onPick: (v: string) => void }) {
  const active = items.filter(s => s.implemented);
  const planned = items.filter(s => !s.implemented);
  return (
    <nav className="service-nav" aria-label="Servizi editoriali">
      <span className="nav-label">Disponibili</span>
      {active.map((s, index) => (
        <button key={s.id} className={`service-item ${value === s.id ? 'selected' : ''}`} onClick={() => onPick(s.id)} aria-pressed={value === s.id}>
          <span className="service-index">{String(index + 1).padStart(2, '0')}</span><span>{s.label}</span><i aria-hidden="true" />
        </button>
      ))}
      <span className="nav-label planned-label">In programma</span>
      {planned.map(s => (
        <div key={s.id} className="service-item planned" title={s.description}>
          <span className="service-index">—</span><span>{s.label}</span><small>Da implementare</small>
        </div>
      ))}
    </nav>
  );
}
