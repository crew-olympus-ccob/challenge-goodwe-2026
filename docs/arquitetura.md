# Arquitetura

Um único processo Python. A interface roda na thread principal (tkinter) e o restante em threads de fundo.

```
 ┌──────────────── interface tkinter (evcharge/ui) ────────────────┐
 │  Portal do morador            Painel do síndico                 │
 └───────────────▲─────────────────────────────────────────────────┘
                 │ consultas (services/queries.py)
          ┌──────┴──────┐
          │  SQLite     │◄── agendador (runtime.py): IA de hora em hora, faturas no início do mês
          └──────▲──────┘
                 │ grava sessões, leituras, alertas
        ┌────────┴─────────┐
        │ Poller (core/)   │  lê cada carregador 1×/s, responde RFID, aplica limite de corrente
        └────────▲─────────┘
                 │ Modbus TCP (FC03 / FC06 / FC16)
   ┌─────────────┴──────────────┐
   │ Simulador (hardware/)      │  3 carregadores virtuais = servidores Modbus em 127.0.0.1
   │ CH-01 11 kW · CH-02 11 kW  │  ← trocar por GoodWe HCA G2 real = mudar host/porta
   │ CH-03 7,4 kW               │
   └────────────────────────────┘
```

## Camadas

| Pasta | Responsabilidade |
|---|---|
| `hardware/` | **Mock do hardware.** `registers.py` (mapa de registradores, fictício), `modbus.py` (servidor e cliente Modbus TCP em socket puro), `charger.py` (física do carregador e do veículo), `simulator.py` (relógio acelerável + servidores), `scenarios.py` (roteiros de demonstração). |
| `core/` | Regras de negócio. `gateway.py` converte registradores em leituras; `sessions.py` é a máquina de estados da sessão (AUTORIZADA → CARREGANDO → CARGA_COMPLETA → FINALIZADA, ou FALHA/CANCELADA); `billing.py` calcula energia + ociosidade; `invoices.py` fecha o mês; `poller.py` faz o laço de leitura; `auth.py` senhas com PBKDF2. |
| `ai/` | IA 1 (`forecast.py`): carga horária, modelo de média por dia×hora e regressão linear; escolhe o de menor erro nos últimos 14 dias e sugere limite de corrente quando a previsão passa de 70% da capacidade. IA 2 (`anomaly.py`): regras explicáveis + Isolation Forest implementado em Python puro. `history.py` gera 90 dias de histórico com anomalias injetadas para medir a detecção. |
| `services/` | Consultas prontas para as telas e integrações (SEMS+ simulado, Open Charge Map opcional com `OCM_API_KEY`). |
| `ui/` | `theme.py` (cores do protótipo Figma), `widgets.py` (cartões, botões, tabelas, diálogos), `charts.py` (gráficos em Canvas), `pages/` (uma tela por arquivo). |

## Banco (SQLite, `data/evcharge.db`)

`usuarios`, `cartoes_rfid`, `veiculos`, `carregadores`, `tarifas`, `sessoes`, `leituras`, `faturas`,
`itens_fatura`, `alertas`, `previsoes`, `execucoes_ia`. Valores em dinheiro são gravados como texto
(Decimal) para não perder centavos; datas em ISO UTC.

## Relógio simulado

Os carregadores virtuais têm um registrador de relógio. Na demonstração o relógio anda 60× mais rápido
(1 h por minuto), e o sistema usa o horário do equipamento nas sessões. Ao fim do cenário o relógio volta
sozinho ao horário real. Timeouts de comunicação (resposta ao RFID) continuam em tempo real.
