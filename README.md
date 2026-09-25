# nemo-relay-on-oci

[![Code style: Black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://black.readthedocs.io/)
[![Lint: Pylint](https://img.shields.io/badge/lint-pylint-blue.svg)](https://pylint.readthedocs.io/)
[![Tests: pytest](https://img.shields.io/badge/tests-pytest-blue.svg)](https://docs.pytest.org/)
[![Python: 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)

Raccolta di demo di agenti AI basate su **NeMo Relay di NVIDIA**,
**OCI Generative AI**, **`langchain_oci`** e **LangGraph**.

Il repository è nella fase iniziale: contiene le regole di sviluppo e la
documentazione, ma non ancora demo eseguibili o codice Python.

## Sviluppo spec-driven

Ogni demo parte da una specifica in `specs/`, scritta prima del codice.
La specifica descrive obiettivo, requisiti, architettura, integrazioni,
input/output, configurazione, errori attesi e criteri di accettazione.
I test verificano tali criteri; implementazione e documentazione seguono
la specifica e vengono aggiornate insieme quando cambia il comportamento.

Le regole vincolanti per agenti e contributori sono in [AGENTS.md](AGENTS.md).

## Requisiti prima di ogni commit e del completamento

- Applicare **Black** a tutto il codice Python, inclusi i test, e verificarne
  la formattazione.
- Eseguire **Pylint** sul codice Python e correggere **tutti** i problemi
  segnalati.
- Preparare ed eseguire i test con **pytest** e **pytest-cov**: tutti i test
  devono passare, con coverage del codice applicativo **almeno dell'80%**
  e soglia automatica `--cov-fail-under=80`.
- Aggiornare la documentazione interessata e il [changelog](CHANGELOG.md).
- Controllare il diff e riportare esiti reali dei controlli e coverage.

Questi passaggi sono obbligatori prima di un commit, di un rilascio o di
dichiarare il lavoro «fatto». Non si aggirano errori disabilitando controlli
o abbassando la soglia di coverage.

In questa fase esclusivamente documentale, i controlli Python non sono
applicabili perché manca il codice. Con la prima demo saranno introdotti
dipendenze, configurazione e comandi esatti per Black, Pylint e pytest.
Da quel momento i controlli si applicheranno anche alle modifiche soltanto
documentali.

## Esecuzione delle demo e test

Ogni demo includerà il collegamento alla propria specifica, i prerequisiti,
le versioni delle dipendenze, la configurazione OCI necessaria e i comandi
di esecuzione. I test ordinari useranno simulazioni dei servizi esterni e
non richiederanno credenziali o chiamate a pagamento; gli eventuali test di
integrazione avranno istruzioni separate.

Non inserire credenziali o segreti nel repository.
