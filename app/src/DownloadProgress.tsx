import { useEffect, useState } from 'react';

export function DownloadProgress({ jobIds, api, onDone }: { jobIds: string[]; api: string; onDone: () => void }) {
  const [pct, setPct] = useState<number | null>(null);
  const [label, setLabel] = useState('');
  useEffect(() => {
    if (!jobIds.length) return;
    setPct(0);
    let stop = false;
    async function tick() {
      let sum = 0, finished = 0, error = '';
      for (const job of jobIds) {
        try {
          const d = await fetch(`${api}/status/${job}`).then(r => r.json());
          sum += d.progress ?? 0;
          if (d.status === 'done') finished++;
          else if (d.status === 'error') { finished++; error = d.error ?? error; }
        } catch { /* riprova */ }
      }
      if (stop) return;
      setPct(Math.round(sum / jobIds.length * 100));
      setLabel(error || `${finished} di ${jobIds.length} completati`);
      if (finished === jobIds.length) { onDone(); return; }
      setTimeout(tick, 1000);
    }
    tick();
    return () => { stop = true; };
  }, [jobIds.join(','), api]);
  if (!jobIds.length || pct === null) return null;
  return <section className="side-panel progress-panel"><div className="panel-heading compact"><div><span className="section-kicker">In corso</span><h2>Download</h2></div><strong>{pct}%</strong></div><progress value={pct} max={100} aria-label={`Download ${pct}%`} /><p>{label}</p></section>;
}
