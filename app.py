# -*- coding: utf-8 -*-
"""Lancador compativel para executar a aplicacao com `python app.py`."""

from conforto_termico.web import (
    _resfriador,
    app,
    calculo_ict_service,
    historico_grafico_service,
    sensor_simulado_service,
)


if __name__ == "__main__":
    app.run(debug=True)
