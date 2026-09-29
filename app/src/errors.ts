export function itError(detail: string, status?: number): string {
  if (!detail) return 'Qualcosa non ha funzionato. Riprova.';
  if (status === 401 || /password|unauthor|401/i.test(detail)) return 'Password errata o sessione scaduta. Riaccedi.';
  if (/connessione|network|fetch/i.test(detail)) return 'Controlla la connessione e che il programma sia avviato.';
  return detail;
}
