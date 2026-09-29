# Book Downloader

Interfaccia per scaricare i propri libri digitali dai servizi supportati. Al momento si avvia dal codice sorgente nel browser: non c'è un installer Windows o macOS da scaricare.

## Prima di iniziare

1. Installa [Python 3.11](https://www.python.org/downloads/) e [Node.js LTS](https://nodejs.org/en/download). Su Windows, durante l'installazione di Python, abilita il launcher `py` se richiesto.
2. In questa pagina GitHub clicca **Code → Download ZIP**, poi estrai lo ZIP. I comandi qui sotto vanno eseguiti nella cartella estratta, quella che contiene `app` e `sidecar`.
3. Apri due terminali in quella cartella e segui la sezione del tuo sistema operativo. Mantienili aperti mentre usi l'app. Su Windows puoi aprire PowerShell scrivendo `powershell` nella barra degli indirizzi della cartella; su Mac puoi digitare `cd ` nel Terminale, trascinare la cartella nella finestra e premere Invio.

## Windows (PowerShell)

Nel primo terminale avvia il servizio Python:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r sidecar\requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
cd sidecar
..\.venv\Scripts\python.exe sidecar_api.py
```

Nel secondo terminale, dalla cartella estratta:

```powershell
npm ci --prefix app
npm run dev --prefix app
```

## macOS (Terminale)

Nel primo terminale avvia il servizio Python:

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install -r sidecar/requirements.txt
.venv/bin/python -m playwright install chromium
cd sidecar
../.venv/bin/python sidecar_api.py
```

Nel secondo terminale, dalla cartella estratta:

```bash
npm ci --prefix app
npm run dev --prefix app
```

Nel primo terminale deve apparire `READY port=8923`. Poi apri **http://localhost:1420** nel browser. Scegli il servizio, accedi e scarica i libri. Per fermare l'app premi `Ctrl+C` in entrambi i terminali. Se una porta è occupata, chiudi eventuali istanze già aperte e riprova. Il primo avvio richiede Internet per installare le dipendenze e Chromium; i download dei libri richiedono la connessione ai servizi.

Questo avvia l'interfaccia nel browser, senza installare un'app nel menu Start o nella cartella Applicazioni. Per la cartella dei PDF e altre indicazioni consulta la [guida utente](docs/GUIDA-UTENTE.md).
