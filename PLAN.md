# PLAN.md — App Download Libri Digitali

**Versione**: 0.1.0
**Stato**: In Corso (scaffold MVP 0.1.0 pronto)
**Data Inizio**: [DATA]
**Target**: Utenti non tecnici su macOS e Windows
**Budget**: €0 (tutto gratis)

## Legenda
- `[ ]` Task da completare
- `[x]` Task completato
- `[~]` Task in corso / parziale
- `[!]` Task bloccato

## Stack Tecnologico

| Componente | Tecnologia | Costo |
|---|---|---|
| Desktop Shell | Tauri 2.0 | Gratis (MIT/Apache) |
| Frontend | React + TypeScript | Gratis |
| Backend/Core | Python 3.10+ (refactoring di pdfgrabber) | Gratis |
| Packaging Python | PyInstaller (sidecar) | Gratis |
| Comunicazione | HTTP locale (FastAPI) | Gratis |
| Automazione browser | Playwright (per Kitaboo/Reader+) | Gratis |
| Storage credenziali | keyring Python | Gratis |
| CI/CD | GitHub Actions (pubblico) | Gratis |
| Distribuzione Windows | Installer NSIS non firmato + docs | Gratis |
| Distribuzione macOS | `.dmg` con ad-hoc signing + docs | Gratis |

**Nota importante sul budget €0:**
- **Windows**: installer non firmato → SmartScreen avvisa al primo avvio ("Ulteriori informazioni" → "Esegui comunque"). Unica opzione gratuita possibile. Se il progetto è open source, si può valutare **SignPath Foundation** (firma gratuita per progetti OSI-approved).
- **macOS**: ad-hoc signing (`-`) obbligatorio per Apple Silicon, evita l'errore fuorviante "app danneggiata". L'utente dovrà fare **clic destro → Apri → Apri** al primo avvio (una volta sola). La notarizzazione Apple ($99/anno) non è compatibile col budget €0, quindi si documenta la procedura di apertura.

---

## Fase 0: Ricognizione e Setup

### 0.1 Analisi dei tool esistenti
- [ ] Clonare `djlight/pdfgrabber`, analizzare `main.py`, `lib.py`, `services/`
- [ ] Clonare `Leone25/zanichelli-downloader`
- [ ] Clonare `vvettoretti/hubscuola-downloader`
- [ ] Verificare licenze di ogni repo (MIT/GPL?) per uso in app derivata
- [x] Documentare servizi e stato: Zanichelli / laZ Ebook, HUB Scuola, bSmart; Pearson eText/Reader+, Oxford, Laterza diBook e Raffaello Player da implementare
- [ ] Documentare per ogni servizio: tipo login, scadenza token, necessità Playwright

### 0.2 Skill discovery
- [ ] Eseguire `npx skills find tauri sidecar`
- [ ] Eseguire `npx skills find python pyinstaller`
- [ ] Eseguire `npx skills find browser automation`
- [ ] Eseguire `npx skills find desktop ui`
- [ ] Documentare skill trovate e applicarle

### 0.3 Setup progetto Tauri
- [x] Inizializzare progetto Tauri 2.0 (`pnpm create tauri-app`)
- [x] Configurare struttura cartelle: `src-tauri/binaries/`, `sidecar/`, `app/`
- [x] Configurare `tauri.conf.json` con `externalBin` per sidecar
- [x] Configurare `capabilities/default.json` per permessi sidecar

---

## Fase 1: Core Downloader (Backend Python)

### 1.1 Refactoring pdfgrabber come libreria
- [x] Estrarre logica da `main.py` in modulo `core.py` con classe `BookDownloader`
- [x] Interfaccia unificata: `download(service, credentials, book_id) → pdf_path`
- [x] Isolare gestione login/token per servizio in classi separate
- [ ] Migliorare gestione eccezioni (TODO di pdfgrabber)

### 1.2 Sidecar API
- [x] Creare `sidecar_api.py` con FastAPI minimale
- [x] Endpoint: `POST /login`
- [x] Endpoint: `GET /services`
- [x] Endpoint: `GET /books?service=X`
- [x] Endpoint: `POST /download`
- [x] Endpoint: `GET /status/{job_id}`
- [x] Endpoint: `GET /health`
- [x] Configurare CORS per webview Tauri (localhost)
- [x] Logging su file locale per debug

### 1.3 Supporto servizi prioritari (MVP)
- [x] **Zanichelli / laZ Ebook**: integrare libreria MyZanichelli e formati Booktab/Kitaboo
- [x] **HubScuola**: integrare da hubscuola-downloader
- [x] **bSmart**: da pdfgrabber
- [ ] **Pearson eText + Reader+**: da implementare

### 1.4 Gestione sessioni e credenziali
- [x] Storage sicuro con keyring Python (macOS Keychain, Windows Credential Manager)
- [x] Salvataggio token tra sessioni
- [x] UI form credenziali per-servizio

---

## Fase 2: Sidecar Packaging

### 2.1 PyInstaller build
- [x] Creare `build_sidecar.py`
- [ ] Compilare `sidecar_api.py` → eseguibile standalone
- [x] Includere dipendenze: playwright, requests, beautifulsoup4, fastapi, keyring
- [x] Gestire bundling browser Chromium (o download al primo avvio)
- [ ] Build per macOS (x86_64 + arm64)
- [ ] Build per Windows (x86_64)
- [ ] Testare eseguibile su entrambe le piattaforme

### 2.2 Integrazione Tauri
- [x] Aggiungere `externalBin: ["binaries/api"]` in `tauri.conf.json`
- [ ] Rinominare eseguibile con target triple (`api-x86_64-apple-darwin`, `api-x86_64-pc-windows-msvc`)
- [x] Spawnare sidecar da Rust all'avvio app
- [x] Shutdown sidecar alla chiusura app
- [x] Gestione porta dinamica (evitare conflitti)

---

## Fase 3: Interfaccia Utente

### 3.1 Design UI
- [x] Wireframe schermata principale: lista libri scaricati
- [x] Pulsante grande **"Aggiungi Libro"** → wizard
- [x] Wizard: seleziona servizio → credenziali → scegli libro → scarica
- [x] Barra progresso download + notifiche stato
- [x] Testi in italiano semplice, zero gergo tecnico

### 3.2 Implementazione frontend
- [x] Setup React + TypeScript in `app/`
- [x] Componente `ServiceSelector`
- [x] Componente `CredentialForm` (adattivo per servizio)
- [x] Componente `BookList`
- [x] Componente `DownloadProgress`
- [x] Componente `SettingsPanel` (gestione account salvati)
- [x] Chiamate HTTP a `http://localhost:PORT/...`

### 3.3 UX per non-tecnici
- [x] Tooltip esplicativi per ogni campo
- [x] Messaggi errore chiari ("Password errata" invece di "401 Unauthorized")
- [x] Nessun terminale visibile
- [x] Auto-avvio sidecar trasparente
- [x] Onboarding al primo avvio

---

## Fase 4: Testing

### 4.1 Test funzionali
- [x] Download Zanichelli (formati Booktab/Kitaboo)
- [x] Download HubScuola
- [x] Download bSmart
- [ ] Gestione sessione Pearson
- [x] Gestione errore credenziali errate

### 4.2 Test cross-platform
- [ ] Build e test su Windows 10/11
- [ ] Build e test su macOS Intel
- [ ] Build e test su macOS Apple Silicon

### 4.3 Test utente reale
- [ ] Far provare a persona senza competenze informatiche
- [ ] Raccogliere feedback
- [ ] Iterare UI

---

## Fase 5: Distribuzione (Budget €0)

### 5.1 Windows — gratis, non firmato
- [x] Configurare bundle NSIS in `tauri.conf.json`
- [x] **Non firmare** (nessun costo)
- [ ] Preparare guida utente con screenshot: come bypassare SmartScreen
  - Istruzioni: "Windows protegge il PC" → clic "Ulteriori informazioni" → "Esegui comunque"
- [ ] Testare installazione da zero (no Python, no admin)
- [ ] (Opzionale, solo se progetto open source) Valutare applicazione a **SignPath Foundation** per firma gratuita OSI-approved
- [ ] [!] Firma codice EV/Azure → **esclusa dal budget €0**

### 5.2 macOS — ad-hoc signing
- [x] Configurare **ad-hoc signing** in Tauri (`signingIdentity: "-"` o equivalente)
- [x] Obbligatorio per Apple Silicon: senza firma valida → errore "app danneggiata"
- [x] Generare `.dmg`
- [ ] Preparare guida utente con screenshot: come aprire al primo avvio
  - Istruzioni: **clic destro sull'app → "Apri" → "Apri"** (una sola volta)
- [ ] Testare installazione da zero
- [ ] [!] Notarizzazione Apple ($99/anno) → **esclusa dal budget €0**
- [ ] [!] Certificato Developer ID → **escluso dal budget €0**

### 5.3 CI/CD (gratis su repo pubblici)
- [x] GitHub Actions per build Windows (runner `windows-latest`)
- [x] GitHub Actions per build macOS (runner `macos-latest`)
- [x] Build sidecar su ciascuna piattaforma (no cross-compile PyInstaller)
- [x] Release automatica con artefatti (`.msi`, `.dmg`)
- [ ] Verificare minuti GitHub Actions gratuiti per repo pubblici (illimitati)

### 5.4 Documentazione
- [x] Guida rapida utente con screenshot (inclusa procedura apertura prima volta)
- [x] FAQ servizi supportati
- [x] Pagina "Perché Windows/Mac mostra un avviso" con istruzioni
- [x] Note legali (uso personale, rispetto ToS)

---

## Rischi e Mitigazioni

| Rischio | Mitigazione |
|---|---|
| Token dei servizi scadono | Richiedi credenziali solo quando necessario |
| PyInstaller + Playwright bundle grande | Download Chromium al primo avvio |
| Servizi cambiano API | Architettura modulare per aggiornare singolo servizio |
| SmartScreen su Windows non firmato | Documentazione chiara con screenshot passo-passo |
| Gatekeeper su macOS blocca app | Ad-hoc signing + documentazione "clic destro → Apri" |
| PyInstaller no cross-compile | Build su ogni piattaforma target via GitHub Actions |
| Utente si spaventa per avviso sicurezza | Onboarding in-app la prima volta + FAQ dedicata |

---

## Prossimi Passi Immediati
1. Eseguire skill discovery (`npx skills find ...`)
2. Clonare e analizzare i 3 repo di riferimento
3. Setup progetto Tauri + sidecar "hello world"
4. Verificare comunicazione Tauri ↔ Python end-to-end
5. Configurare ad-hoc signing macOS e bundle NSIS Windows
6. Refactoring primo servizio (Zanichelli Booktab)
7. MVP end-to-end: login → lista libri → download → PDF salvato
