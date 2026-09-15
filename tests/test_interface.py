"""Abre a interface, entra como síndico e como morador e abre todas as telas.

É pulado automaticamente quando não há tela disponível (ex.: servidor sem monitor).
"""

from __future__ import annotations

import gc
import tempfile
import time
import unittest
from pathlib import Path

try:
    import tkinter as tk

    _raiz = tk.Tk()
    _raiz.destroy()
    del _raiz
    TEM_TELA = True
except Exception:  # noqa: BLE001
    TEM_TELA = False


@unittest.skipUnless(TEM_TELA, "sem tela disponível para o tkinter")
class TestInterface(unittest.TestCase):
    def setUp(self):
        from evcharge.runtime import Sistema
        from evcharge.ui.app import App

        self.pasta = tempfile.TemporaryDirectory()
        self.sistema = Sistema(Path(self.pasta.name) / "ui.db")
        self.app = App(self.sistema)
        self.app.withdraw()
        self.erros: list[BaseException] = []
        self.app.report_callback_exception = lambda e, v, tb: self.erros.append(v)
        # espera a tela de carregamento terminar (banco + histórico) e chegar ao login
        limite = time.monotonic() + 60
        while self.sistema.poller is None and time.monotonic() < limite:
            self.app.update()
            time.sleep(0.05)
        self.assertIsNotNone(self.sistema.poller, "o sistema não terminou de iniciar")

    def tearDown(self):
        self.app.fechar()
        # o Tcl exige que os objetos do tkinter sejam liberados na thread principal
        del self.app
        gc.collect()
        self.pasta.cleanup()

    def _entrar_e_abrir_tudo(self, email: str, senha: str, menu) -> None:
        from evcharge.core.auth import autenticar

        self.app.usuario = autenticar(self.sistema.db, email, senha)
        self.assertIsNotNone(self.app.usuario)
        self.app.tela_principal()
        for _, nome, _ in menu:
            self.app.abrir(nome)
            self.app.update()
            self.app.pagina_atual.atualizar()
            self.app.update()
        self.assertEqual(self.erros, [])

    def test_telas_do_sindico(self):
        from evcharge.ui.app import MENU_ADMIN

        self._entrar_e_abrir_tudo("admin@condominio.local", "admin123", MENU_ADMIN)

    def test_telas_do_morador(self):
        from evcharge.ui.app import MENU_MORADOR

        self._entrar_e_abrir_tudo("morador1@condominio.local", "morador123", MENU_MORADOR)


if __name__ == "__main__":
    unittest.main()
