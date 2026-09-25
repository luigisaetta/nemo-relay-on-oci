# Istruzioni per agenti e contributori

Queste regole si applicano a tutto il repository `nemo-relay-on-oci`.

## Obiettivo e tecnologie

Il repository raccoglie demo di agenti AI basate su:

- NeMo Relay, la libreria NVIDIA;
- OCI Generative AI;
- `langchain_oci`;
- LangGraph.

Ogni demo deve spiegare lo scopo, le integrazioni utilizzate e come eseguirla.
Non inventare API o compatibilità: verificarle nella documentazione ufficiale
e dichiarare le versioni delle dipendenze utilizzate.

## Approccio spec-driven

1. Prima di implementare o modificare un comportamento, creare o aggiornare
   la specifica corrispondente in `specs/`.
2. Descrivere nella specifica obiettivo, requisiti, ambito ed esclusioni,
   architettura e integrazioni, input/output, configurazione, gestione degli
   errori e criteri di accettazione verificabili.
3. Definire i casi di test a partire dai criteri di accettazione, inclusi
   percorsi di errore e casi limite.
4. Implementare quanto previsto dalla specifica e mantenere tracciabili i
   collegamenti tra specifica, demo e test.
5. Se cambia il comportamento richiesto, aggiornare prima la specifica,
   poi implementazione, test e documentazione.

Per modifiche esclusivamente documentali, mantenere coerenti i documenti
coinvolti; non occorre una specifica di funzionalità inesistente.

## Controlli obbligatori prima di ogni commit e del completamento

Prima di effettuare un commit, rilasciare modifiche o dichiarare il lavoro
«fatto», completare tutti i seguenti passaggi:

1. **Formattazione:** applicare Black a tutto il codice Python, inclusi i
   test, e verificare che una successiva esecuzione in modalità check passi.
2. **Analisi statica:** eseguire Pylint su tutto il codice Python, inclusi i
   test, e correggere **tutti** i problemi segnalati. Un controllo della sola
   sintassi non sostituisce Pylint. Il comando deve terminare con successo,
   senza segnalazioni irrisolte.
3. **Test e coverage:** preparare o aggiornare i test e lanciarli con pytest
   e pytest-cov. Tutti i test devono passare e la copertura complessiva del
   codice applicativo deve essere **almeno dell'80%**, con soglia automatica
   `--cov-fail-under=80`. Misurare anche i moduli applicativi non importati
   dai test; non includere i test nel denominatore della coverage.
4. **Documentazione:** aggiornare README e documentazione interessata con
   comportamento, configurazione, prerequisiti e istruzioni di esecuzione
   pertinenti alle modifiche.
5. **Changelog:** aggiornare `CHANGELOG.md`, descrivendo le modifiche nella
   sezione `Unreleased` fino alla preparazione di una release.
6. **Verifica finale:** controllare il diff e riportare i comandi eseguiti,
   gli esiti e la percentuale di coverage realmente misurata.

Non abbassare la soglia di coverage, escludere codice per aggirarla,
disabilitare controlli Pylint o saltare test per far passare i controlli.
Se un controllo fallisce, correggere la causa e ripeterlo prima del commit
o della dichiarazione di completamento. Se è bloccato dall'ambiente,
segnalare il blocco senza dichiarare soddisfatti i requisiti.

Finché il repository contiene soltanto documentazione e nessun file Python,
Black, Pylint, pytest e coverage non hanno codice su cui operare: indicare
esplicitamente questa condizione nel resoconto, senza inventare esiti o
creare test fittizi. Alla prima introduzione di codice Python configurare
ed eseguire tutti i controlli sopra descritti. Una modifica documentale in
un repository che contiene già codice Python non esonera dai controlli.

## Configurazione e riproducibilità

- Con la prima demo introdurre la configurazione degli strumenti e le
  dipendenze di sviluppo, includendo `black`, `pylint`, `pytest` e
  `pytest-cov`, e documentare i comandi esatti nel README.
- Configurare la coverage su tutte le directory applicative. Esempio da
  adattare alla struttura effettiva: `pytest --cov=src --cov-report=term-missing
  --cov-fail-under=80`.
- I test automatici ordinari devono essere riproducibili senza credenziali
  OCI, accesso alla rete o chiamate a pagamento: simulare i servizi esterni.
- Separare ed esplicitare prerequisiti e comandi degli eventuali test di
  integrazione con servizi reali.
- Non versionare credenziali, chiavi, token o altri segreti. Documentare la
  configurazione mediante esempi privi di valori sensibili.
