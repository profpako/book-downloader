export function Onboarding({ onClose }: { onClose: () => void }) {
  if (localStorage.getItem('bd-onboarded')) return null;
  return <section className="onboarding"><div><span className="section-kicker">Primo avvio</span><strong>Tre passaggi, poi fa tutto l’app.</strong><p>Scegli il servizio, accedi e seleziona i libri da salvare.</p></div><button className="button text-button" onClick={() => { localStorage.setItem('bd-onboarded', '1'); onClose(); }}>Ho capito</button></section>;
}
