# Book Downloader

Interfaccia per scaricare i propri libri digitali dai servizi supportati. L'app funziona nel browser, ma tutti i dati e i processi restano sul computer dell'utente.

## Installazione rapida

Serve una connessione Internet durante la prima installazione. Non occorre installare manualmente Python, Node.js o Chromium: gli script controllano il computer e preparano ciò che manca.

| Sistema | File da aprire |
|---|---|
| macOS | `INSTALLA_MAC.command` |
| Windows 10/11 | `INSTALLA_WINDOWS.bat` |

### 1. Scarica ed estrai il progetto

1. In questa pagina GitHub premi **Code**, poi **Download ZIP**.
2. Apri il file ZIP scaricato e attendi che venga estratto completamente.
3. Apri la cartella estratta, quella che contiene `INSTALLA_MAC.command` e `INSTALLA_WINDOWS.bat`.

Non avviare i file direttamente dall'anteprima del ZIP: devono trovarsi in una normale cartella del computer.

### 2A. Installa su macOS

1. Fai doppio clic su **INSTALLA_MAC.command**.
2. Se macOS chiede conferma, scegli **Apri**. Se il doppio clic viene bloccato, fai clic destro sul file, scegli **Apri** e conferma di nuovo.
3. Lascia aperta la finestra del Terminale. Se viene richiesta la password del Mac, digitala e premi Invio: mentre scrivi la password non compaiono caratteri, ed è normale.
4. Attendi il messaggio `Installazione completata`. Il browser si aprirà automaticamente su **http://localhost:1420**.

Se il file non parte con il doppio clic, apri Terminale, scrivi `cd ` con uno spazio finale, trascina la cartella del progetto dentro la finestra, premi Invio e poi esegui:

```bash
bash install_mac.sh
```

### 2B. Installa su Windows

1. Fai doppio clic su **INSTALLA_WINDOWS.bat**.
2. Se Windows chiede di consentire l'installazione di un componente ufficiale, conferma.
3. Lascia aperta la finestra. Lo script può installare il gestore Python ufficiale per il solo utente corrente; non occorre configurare variabili d'ambiente.
4. Attendi il messaggio `Installazione completata`. Il browser si aprirà automaticamente su **http://localhost:1420**.

Se il doppio clic non funziona, apri la cartella, fai clic nella barra dell'indirizzo, scrivi `powershell` e premi Invio. Poi esegui:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install_windows.ps1
```

## Cosa fa l'installer

L'installer:

1. riutilizza un Python compatibile già presente (da 3.10 a 3.14);
2. se Python manca o è incompatibile, installa Python 3.14, la release stabile corrente supportata dal progetto;
3. riutilizza una versione supportata di Node.js oppure installa Node.js 24 LTS su macOS e l'ultima LTS ufficiale disponibile su Windows;
4. crea l'ambiente isolato `.venv` senza modificare i pacchetti Python dell'utente;
5. installa le dipendenze Python, Chromium per Playwright e i pacchetti dell'interfaccia;
6. avvia il servizio locale e apre il browser.

Su macOS le dipendenze mancanti vengono installate tramite [Homebrew](https://brew.sh/); se Homebrew non esiste, viene installato dal suo script ufficiale. Su Windows Python viene ottenuto tramite il [Python Install Manager ufficiale](https://docs.python.org/3/using/windows.html) e Node.js dagli archivi ufficiali, verificandone il checksum SHA-256.

## Avvii successivi

Puoi aprire di nuovo lo stesso file usato per l'installazione:

- macOS: **INSTALLA_MAC.command**;
- Windows: **INSTALLA_WINDOWS.bat**.

Lo script ricontrolla l'ambiente e riusa tutto ciò che è già installato. Per fermare l'app premi `Ctrl+C` nella finestra che è rimasta aperta. La finestra deve restare aperta mentre usi Book Downloader.

## Uso

Quando si apre **http://localhost:1420**:

1. scegli il servizio;
2. inserisci le credenziali del tuo account;
3. aggiorna la libreria;
4. seleziona e scarica i libri.

Le credenziali vengono salvate nel portachiavi sicuro del sistema operativo. Per la cartella dei PDF e le altre funzioni consulta la [guida utente](docs/GUIDA-UTENTE.md) e le [domande frequenti](docs/FAQ.md).

## Problemi comuni

### Il browser non si apre

Apri manualmente **http://localhost:1420**. Se la pagina non risponde, controlla che la finestra dell'installer sia ancora aperta e non mostri un errore.

### La porta 1420 o 8923 è già occupata

Chiudi le altre finestre di Book Downloader e rilancia lo script. Se il problema continua, riavvia il computer e riprova.

### Il download di una dipendenza fallisce

Controlla la connessione Internet, disattiva temporaneamente eventuali VPN o proxy aziendali e rilancia lo stesso file. Le installazioni già completate verranno riutilizzate.

### macOS blocca il file

Usa **clic destro → Apri**. Se continua a non partire, usa il comando `bash install_mac.sh` mostrato sopra. Homebrew supporta soltanto versioni di macOS ancora mantenute; su un Mac molto vecchio potrebbe essere necessario aggiornare macOS.

### Windows non trova App Installer

Lo script prova anche il metodo ufficiale alternativo di python.org. Se Windows blocca entrambi i metodi, installa o aggiorna **App Installer** dal Microsoft Store, riavvia il computer e rilancia `INSTALLA_WINDOWS.bat`. WinGet è supportato da Windows 10 versione 1809 o successiva e Windows 11.

### L'installazione si interrompe ancora

Non chiudere subito la finestra: l'ultima riga indica il componente che ha fallito. Conserva il testo completo dell'errore insieme al nome e alla versione del sistema operativo; sono le informazioni necessarie per ricevere assistenza.

## Avvio manuale per sviluppatori

Dopo che l'installer ha completato almeno una volta, su macOS puoi usare:

```bash
bash start_app.sh
```

Su Windows è sufficiente rilanciare `INSTALLA_WINDOWS.bat`. Il frontend può essere verificato separatamente con:

```bash
npm run build --prefix app
```

Chi usa un ambiente Python macOS esterno può creare `.env.local` nella cartella del progetto:

```bash
export BOOK_DOWNLOADER_PYTHON="/percorso/ambiente/bin/python"
export PLAYWRIGHT_BROWSERS_PATH="/percorso/browser/playwright"
```

Questa configurazione avanzata viene letta da `start_app.sh`, non è necessaria per l'installazione normale.
