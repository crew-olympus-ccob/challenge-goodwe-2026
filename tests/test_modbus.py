import unittest

from evcharge.hardware import registers as R
from evcharge.hardware.modbus import ModbusClient, ModbusConnectionError, ModbusError, ModbusServer, RegisterBank


class TestRegistradores(unittest.TestCase):
    def test_codifica_e_decodifica(self):
        self.assertEqual(R.decode("energy_wh", R.encode("energy_wh", 123456789)), 123456789)
        self.assertAlmostEqual(R.decode("current_a", R.encode("current_a", 15.94)), 15.94)
        self.assertEqual(R.decode("rfid_uid", R.encode("rfid_uid", "AB120001")), "AB120001")
        self.assertEqual(R.STATUS[4], "CARREGANDO")

    def test_leituras_cobrem_todos_os_registradores(self):
        cobertos = {a for ini, n in R.read_ranges() for a in range(ini, ini + n)}
        for nome in R.REGISTROS:
            self.assertTrue(set(range(R.address(nome), R.address(nome) + R.size(nome))) <= cobertos, nome)


class TestModbusTCP(unittest.TestCase):
    def test_leitura_escrita_e_protecao(self):
        escritas = []
        banco = RegisterBank(64, writable={50, 51}, on_write=lambda a, v: escritas.append((a, v)))
        banco.set(10, [1, 2, 3])
        srv = ModbusServer(banco, "127.0.0.1", 0)
        srv.start()
        try:
            cli = ModbusClient("127.0.0.1", srv.port)
            self.assertEqual(cli.read(10, 3), [1, 2, 3])
            cli.write(50, [7, 8])
            cli.write(51, [9])
            self.assertEqual(cli.read(50, 2), [7, 9])
            with self.assertRaises(ModbusError):
                cli.write(10, [1])  # somente leitura
            with self.assertRaises(ModbusError):
                cli.read(60, 10)  # fora do banco
            cli.close()
        finally:
            srv.stop()
        self.assertEqual(escritas, [(50, [7, 8]), (51, [9])])

    def test_sem_servidor(self):
        with self.assertRaises(ModbusConnectionError):
            ModbusClient("127.0.0.1", 1, timeout=0.5).read(0, 1)


if __name__ == "__main__":
    unittest.main()
