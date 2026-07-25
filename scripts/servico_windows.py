# -*- coding: utf-8 -*-
r"""
servico_windows.py
=====================
Esqueleto de serviço nativo do Windows para o coletor, via `pywin32`
(`win32serviceutil.ServiceFramework`) -- integra de verdade com o
Service Control Manager e o Visualizador de Eventos do Windows, ao
contrário do NSSM (que só supervisiona um processo de fora).

Passo seguinte ao NSSM (`scripts/instalar_servico_coletor.ps1`), não uma
substituição imediata: exige `pip install pywin32` e mais alguns passos
manuais de registro. "Por enquanto" (ver README), o caminho recomendado
para começar é o NSSM -- este arquivo existe para quando fizer sentido
evoluir.

Roda o MESMO `run_coletor.py` de sempre por dentro do serviço -- nada no
resto do projeto precisa saber que está rodando como serviço nativo em
vez de em primeiro plano.

USO (PowerShell como Administrador, com pywin32 instalado):
    python scripts\servico_windows.py install
    python scripts\servico_windows.py start
    python scripts\servico_windows.py stop
    python scripts\servico_windows.py remove

Ver também: https://github.com/mhammond/pywin32
"""

from __future__ import annotations

import os
import sys
import threading

try:
    import servicemanager
    import win32event
    import win32service
    import win32serviceutil
except ImportError:  # pragma: no cover -- so existe com pywin32 instalado
    print(
        "pywin32 não está instalado. Rode 'pip install pywin32' antes de "
        "usar este script (ver docstring do módulo)."
    )
    raise

PROJETO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJETO_DIR not in sys.path:
    sys.path.insert(0, PROJETO_DIR)

from app.app_factory import AppConfig, criar_app_coletor, executar_coletor


class ServicoColetor(win32serviceutil.ServiceFramework):
    _svc_name_ = "ConfortoTermicoColetor"
    _svc_display_name_ = "ConfortoTermico - Coletor"
    _svc_description_ = (
        "Lê sensores, calcula o índice de conforto e aciona equipamentos "
        "(ConfortoTermico). Reinicia junto do Windows."
    )

    def __init__(self, args):
        super().__init__(args)
        self._evento_parar = win32event.CreateEvent(None, 0, 0, None)
        self._thread_servidor: threading.Thread | None = None

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        # `executar_servidor` (app_factory.py) para o gerenciador de
        # controle e a fila de notificacoes no `finally` de dentro dele
        # quando o servidor (waitress/Flask) para -- aqui so sinalizamos
        # a thread deste processo a encerrar; o servidor HTTP em si so
        # sai do loop quando o proprio processo termina (SO encerra o
        # processo do servico ao final de SvcStop), entao o sinal serve
        # so para o SCM saber que o pedido de parada foi recebido.
        win32event.SetEvent(self._evento_parar)
        servicemanager.LogInfoMsg("ConfortoTermicoColetor: parada solicitada.")

    def SvcDoRun(self):
        servicemanager.LogInfoMsg("ConfortoTermicoColetor: iniciando.")
        self.ReportServiceStatus(win32service.SERVICE_RUNNING)

        config = AppConfig.from_env("coletor")
        app = criar_app_coletor(config=config)

        # `executar_servidor` bloqueia (waitress.serve ou app.run) ate o
        # processo ser encerrado -- e exatamente o comportamento que um
        # servico do Windows espera de SvcDoRun (so retornar quando o
        # servico de fato parou).
        try:
            executar_coletor(app, config)
        except Exception:
            servicemanager.LogErrorMsg(
                "ConfortoTermicoColetor: encerrado com erro -- ver log da aplicacao "
                "em instance/ para detalhes."
            )
            raise


if __name__ == "__main__":
    win32serviceutil.HandleCommandLine(ServicoColetor)
