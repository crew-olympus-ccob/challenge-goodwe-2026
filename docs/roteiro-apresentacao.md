# Roteiro de apresentação (pitch / MVP)

## Antes (uma vez)

1. Instale o Python 3.11+ (python.org).
2. Dê dois cliques em `iniciar.bat` e faça o roteiro abaixo uma vez sozinho para sentir o tempo.

Funciona 100% offline.

## No dia

1. `iniciar.bat` (abre em poucos segundos).
2. Entre como **admin** (`admin@condominio.local` / `admin123`).
3. Para mostrar a visão do morador, use **Sair** e entre como `morador2@condominio.local` / `morador123`
   (Bruno, que terá a recarga com ociosidade) — a demonstração continua rodando enquanto você troca de usuário.

## Roteiro (≈ 6 min)

| Tempo | Tela | O que mostrar |
|---|---|---|
| 0:00 | Visão geral | 3 carregadores GoodWe HCA G2; energia, receita e alertas do mês. Clique **▶ Iniciar demonstração**. |
| 0:30 | Visão geral | CH-01 (Ana) e CH-02 (Bruno) começam a carregar; um cartão desconhecido é **negado** no CH-03. |
| 1:30 | Simulador | Os carregadores virtuais: potência, medidor, eventos. "Com o equipamento real é só trocar o IP." |
| 2:00 | Sair → morador2 → Dashboard | Recarga ativa do Bruno: kWh, potência, custo estimado; após a carga completa aparece a **carência** e depois a **taxa de ociosidade**. |
| 3:30 | Sair → admin → Alertas | Ociosidade do CH-02 e **potência acima do nominal** no CH-03 (IA 2). |
| 4:30 | Inteligência | Previsão de pico 24 h (IA 1), modelo escolhido, erro médio e taxa de detecção de anomalias. |
| 5:15 | Faturas e tarifas | Rateio mensal por unidade (energia + ociosidade); regras configuráveis. |

Durante o roteiro o relógio do simulador fica **60× mais rápido** e volta ao normal sozinho no fim.

## Cenários usados

| Carregador | Cartão | O que acontece |
|---|---|---|
| CH-01 | AB120001 (Ana) | recarga normal de 30 kWh, desconecta 5 min após completar |
| CH-02 | AB120002 (Bruno) | 15 kWh e fica 75 min parado → multa por ociosidade |
| CH-03 | FFFFFFFF | cartão não cadastrado → negado |
| CH-03 | AB120003 (Carla) | medidor com defeito reporta potência ×1,35 → alerta de anomalia |

Na tela **Simulador** dá para rodar cada cenário separado, passar cartões, conectar/desconectar veículos e
provocar falhas manualmente.

## Se algo der errado

- Começar do zero: feche e rode `resetar.bat`.
- Erro ao abrir: veja `data/evcharge.log`.
