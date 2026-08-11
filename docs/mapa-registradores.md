# Mapa de registradores Modbus (FICTÍCIO)

Os endereços abaixo foram inventados para o simulador. Quando o manual Modbus do GoodWe HCA G2 estiver
disponível, ajuste **apenas** `evcharge/hardware/registers.py`; nenhum outro arquivo depende dos endereços.

| Nome | Endereço | Tipo | Escala | Acesso | Uso |
|---|---|---|---|---|---|
| status | 0 | uint16 | 1 | leitura | 0 disponível, 1 conectado, 2 aguardando autorização, 3 autorizado, 4 carregando, 5 carga suspensa, 6 falha |
| cable_connected | 1 | uint16 | 1 | leitura | cabo conectado no veículo |
| error_code | 2 | uint16 | 1 | leitura | código de falha |
| phases | 3 | uint16 | 1 | leitura | 1 ou 3 fases |
| power_w | 10 | uint32 | 1 W | leitura | potência instantânea |
| current_a | 12 | uint16 | 0,01 A | leitura | corrente |
| voltage_v | 13 | uint16 | 0,1 V | leitura | tensão |
| energy_wh | 20 | uint32 | 1 Wh | leitura | medidor acumulado |
| device_clock | 30 | uint32 | 1 s | leitura | relógio do equipamento (epoch UTC) |
| rfid_seq | 40 | uint16 | 1 | leitura | incrementa a cada cartão lido |
| rfid_uid | 41–44 | string(8) | — | leitura | UID do cartão |
| auth_result | 50 | uint16 | 1 | escrita | 1 aceito, 2 negado |
| auth_seq | 51 | uint16 | 1 | escrita | qual `rfid_seq` está sendo respondido |
| current_limit_a | 52 | uint16 | 1 A | escrita | limite de corrente (0 = sem limite, mínimo 6 A) |
| max_power_w | 60 | uint32 | 1 W | leitura | potência nominal |

Valores de 32 bits: word mais significativa primeiro. Unit ID 1.

Pontos a confirmar com o fabricante: se o HCA G2 expõe o UID do RFID via Modbus e se aceita autorização
remota (senão, a autorização fica na lista local do carregador ou via SEMS+).
