# Book Downloader

Interfaccia per scaricare i propri libri digitali dai servizi supportati. Al momento si avvia dal codice sorgente nel browser: non c'è un installer Windows o macOS da scaricare.

## Prima di iniziare

1. Servono [Python 3.11](https://www.python.org/downloads/) e [Node.js](https://nodejs.org/en/download). Puoi installarli con i comandi qui sotto o dai link ufficiali.
2. In questa pagina GitHub clicca **Code → Download ZIP**, poi estrai lo ZIP. I comandi qui sotto vanno eseguiti nella cartella estratta, quella che contiene `app` e `sidecar`.
3. Apri due terminali in quella cartella e segui la sezione del tuo sistema operativo. Mantienili aperti mentre usi l'app. Su Windows puoi aprire PowerShell scrivendo `powershell` nella barra degli indirizzi della cartella; su Mac puoi digitare `cd ` nel Terminale, trascinare la cartella nella finestra e premere Invio.

## Windows (PowerShell)

Se `winget` non è disponibile, apri la pagina ufficiale di **App Installer** con questo comando, clicca **Installa** e poi riapri PowerShell:

```powershell
Start-Process "https://apps.microsoft.com/detail/9nblggh4nns1"
```

Se Python e Node.js non sono già installati, apri PowerShell e digita:

```powershell
winget install --id Python.Python.3.11 --exact --source winget
winget install --id OpenJS.NodeJS.LTS --exact --source winget
```

Chiudi e riapri PowerShell, poi controlla che entrambi siano disponibili:

```powershell
py -3.11 --version
node --version
npm --version
```

Se non puoi installare App Installer, installa Python e Node.js dai link sopra; nell'installer Python abilita il launcher `py` se richiesto. Windows potrebbe chiedere di autorizzare l'installazione.

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

Se Python e Node.js non sono già installati, usa [Homebrew](https://brew.sh/) e digita:

```bash
brew install python@3.11 node
python3.11 --version
node --version
npm --version
```

Se non usi Homebrew, installa Python e Node.js dai link sopra. Dopo l'installazione chiudi e riapri Terminale.

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
