"""EV ChargeHub: ponto de entrada.

    python main.py            abre o sistema (cria o banco na primeira vez)
    python main.py --reset    apaga o banco e recomeça do zero
"""

from __future__ import annotations

import argparse
import logging
import sys

from evcharge import config


def main() -> None:
    parser = argparse.ArgumentParser(description=config.APP_NAME)
    parser.add_argument("--reset", action="store_true", help="apaga o banco de dados e gera tudo de novo")
    args = parser.parse_args()

    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.FileHandler(config.DATA_DIR / "evcharge.log", encoding="utf-8"), logging.StreamHandler(sys.stdout)],
    )
    if args.reset:
        for sufixo in ("", "-wal", "-shm"):
            arquivo = config.DB_PATH.with_name(config.DB_PATH.name + sufixo)
            if arquivo.exists():
                arquivo.unlink()
        logging.info("banco apagado; será recriado agora")

    try:
        import tkinter  # noqa: F401
    except ImportError:
        print("Este Python não tem o tkinter. Instale o Python pelo site python.org (marque a opção 'tcl/tk and IDLE').")
        sys.exit(1)

    from evcharge.ui.app import App

    App().mainloop()


if __name__ == "__main__":
    main()
