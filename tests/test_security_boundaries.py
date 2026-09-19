from __future__ import annotations

import pytest

from app.ict import rotas as rotas_ict
from app.seguranca import auth, tokens
from app.seguranca.limites import LimitadorJanela
from app.seguranca.zonas import verificar_acesso_zona


def test_tokens_de_capacidades_nao_sao_intercambiaveis(monkeypatch):
    monkeypatch.setenv("CONFORTO_INTERNO_TOKEN_LEITURA", "raiz-de-teste")
    monkeypatch.setenv("CONFORTO_INTERNO_TOKEN_CONTROLE", "raiz-de-teste")

    leitura = auth.obter_token_interno(tokens.CAPACIDADE_LEITURA)
    controle = auth.obter_token_interno(tokens.CAPACIDADE_CONTROLE)

    assert leitura != controle


def test_token_ausente_falha_fechado_fora_de_desenvolvimento(tmp_path, monkeypatch):
    monkeypatch.delenv("CONFORTO_INTERNO_TOKEN_LEITURA", raising=False)
    monkeypatch.delenv("CONFORTO_INTERNO_TOKEN_LEITURA_FILE", raising=False)
    monkeypatch.delenv("CONFORTO_DEVELOPMENT", raising=False)
    monkeypatch.delenv("CONFORTO_TESTING", raising=False)
    monkeypatch.setattr(tokens, "resolver_segredo", lambda *args, **kwargs: None)
    monkeypatch.setattr(tokens.db, "INSTANCE_DIR", str(tmp_path))

    with pytest.raises(RuntimeError, match="CONFORTO_INTERNO_TOKEN_LEITURA_FILE"):
        auth.obter_token_interno(tokens.CAPACIDADE_LEITURA)

    assert not (tmp_path / "interno_token_leitura.txt").exists()


def test_tokens_de_desenvolvimento_persistem_raizes_independentes(tmp_path, monkeypatch):
    monkeypatch.delenv("CONFORTO_INTERNO_TOKEN_LEITURA", raising=False)
    monkeypatch.delenv("CONFORTO_INTERNO_TOKEN_CONTROLE", raising=False)
    monkeypatch.delenv("CONFORTO_INTERNO_TOKEN_LEITURA_FILE", raising=False)
    monkeypatch.delenv("CONFORTO_INTERNO_TOKEN_CONTROLE_FILE", raising=False)
    monkeypatch.setenv("CONFORTO_DEVELOPMENT", "1")
    monkeypatch.setattr(tokens, "resolver_segredo", lambda *args, **kwargs: None)
    monkeypatch.setattr(tokens.db, "INSTANCE_DIR", str(tmp_path))

    leitura = auth.obter_token_interno(tokens.CAPACIDADE_LEITURA)
    controle = auth.obter_token_interno(tokens.CAPACIDADE_CONTROLE)

    assert leitura != controle
    assert (tmp_path / "interno_token_leitura.txt").read_text(encoding="utf-8")
    assert (tmp_path / "interno_token_controle.txt").read_text(encoding="utf-8")


def test_mapa_do_coletor_exige_capacidade_por_endpoint():
    from app.coletor import rotas

    assert rotas.CAPACIDADE_POR_ENDPOINT["coletor.testar_conexao_interno"] == "leitura"
    assert rotas.CAPACIDADE_POR_ENDPOINT["coletor.comandar_atuador_zona"] == "controle"
    assert "coletor.nova_rota" not in rotas.CAPACIDADE_POR_ENDPOINT


def test_acl_de_zona_atual_e_explicitamente_instalacao_global():
    zona = {"id": 7}
    assert (
        verificar_acesso_zona(
            7,
            perfil="operador",
            area="operacao",
            obter_zona=lambda zona_id: zona if zona_id == 7 else None,
        )
        == "autorizada"
    )
    assert (
        verificar_acesso_zona(
            8,
            perfil="operador",
            area="operacao",
            obter_zona=lambda zona_id: zona if zona_id == 7 else None,
        )
        == "nao_encontrada"
    )


def test_acl_de_zona_exige_concessao_para_usuario_nao_administrador():
    zona = {"id": 7}

    def obter(zona_id):
        return zona if zona_id == 7 else None

    assert verificar_acesso_zona(
        7,
        perfil="operador",
        area="operacao",
        usuario_id=11,
        tem_acesso_zona=lambda usuario_id, zona_id: False,
        obter_zona=obter,
    ) == "negada"
    assert verificar_acesso_zona(
        7,
        perfil="operador",
        area="operacao",
        usuario_id=11,
        tem_acesso_zona=lambda usuario_id, zona_id: True,
        obter_zona=obter,
    ) == "autorizada"


def test_admin_tem_acesso_global_mesmo_sem_linha_de_acl():
    assert verificar_acesso_zona(
        7,
        perfil="administrador",
        area="operacao",
        usuario_id=1,
        tem_acesso_zona=lambda *_: False,
        obter_zona=lambda _zona_id: {"id": 7},
    ) == "autorizada"


def test_limitador_de_analise_recusa_a_quarta_consulta_da_janela():
    limitador = LimitadorJanela(((60, 3),))

    assert [limitador.permitir("usuario", agora=float(i)) for i in range(4)] == [
        True,
        True,
        True,
        False,
    ]


def test_cache_de_analise_tem_ttl_documentado():
    assert rotas_ict.TTL_CACHE_ANALISES_SEGUNDOS == 15.0
    assert rotas_ict.LIMITE_ANALISES_POR_MINUTO == 30
