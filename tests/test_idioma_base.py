"""Persistência e isolamento do idioma antes de ligá-lo à interface."""

import ast
import json
import re
from pathlib import Path
from uuid import uuid4

from sharedauth.session import marca_de_sessao
from werkzeug.datastructures import LanguageAccept
from werkzeug.http import parse_accept_header

from app.dados_entrada.cidades import CATEGORIAS_DENSIDADE, MODELOS_LOTACAO
from app.database.usuarios import atualizar_idioma, criar_usuario, obter_usuario
from app.nucleo import idioma
from app.seguranca import auth
from app.termico import thermal_indices

RAIZ = Path(__file__).resolve().parent.parent


def test_textos_marcados_tem_traducao():
    """Texto novo não deve voltar silenciosamente ao português em inglês."""
    catalogo = json.loads((RAIZ / "app/traducoes/en.json").read_text(encoding="utf-8"))
    marcados = set()
    for caminho in (RAIZ / "app").rglob("*.py"):
        arvore = ast.parse(caminho.read_text(encoding="utf-8"), filename=str(caminho))
        for no in ast.walk(arvore):
            if (
                isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute)
                and no.func.attr == "traduzir" and isinstance(no.func.value, ast.Name)
                and no.func.value.id == "idioma" and no.args
                and isinstance(no.args[0], ast.Constant) and isinstance(no.args[0].value, str)
            ):
                marcados.add(no.args[0].value)
    for caminho in (RAIZ / "app/templates").rglob("*.html"):
        marcados.update(
            match.group(2)
            for match in re.finditer(r"traduzir\(\s*(['\"])(.*?)\1\s*\)", caminho.read_text(encoding="utf-8"))
        )
    for caminho in (RAIZ / "app/static/js").rglob("*.js"):
        if "vendor" not in caminho.parts:
            marcados.update(
                match.group(2)
                for match in re.finditer(r"window\.t\(\s*(['\"])(.*?)\1\s*[,\)]", caminho.read_text(encoding="utf-8"))
            )
    marcados.update({"Ligar %(tipo)s nesta zona?", "Desligar %(tipo)s nesta zona?", "ventilador", "nebulizador"})
    marcados.update({
        "Média, mínimo e máximo a cada 15 min — última %(total)s janela (até 24h).",
        "Média, mínimo e máximo a cada 15 min — últimas %(total)s janelas (até 24h).",
        "Média horária (status calculado a partir da média) — última %(total)s hora (até 7 dias).",
        "Média horária (status calculado a partir da média) — últimas %(total)s horas (até 7 dias).",
        "Leitura bruta, uma a cada ciclo do coletor — última %(total)s leitura.",
        "Leitura bruta, uma a cada ciclo do coletor — últimas %(total)s leituras.",
    })
    marcados.update(thermal_indices.NOME_ESPECIE.values())
    marcados.update(thermal_indices.NOME_INDICE.values())
    marcados.update(thermal_indices.MENSAGENS_STATUS.values())
    marcados.update(campo["label"] for campo in thermal_indices.CAMPO_METADADOS.values())
    marcados.update(categoria["rotulo"] for categoria in CATEGORIAS_DENSIDADE)
    marcados.update(modelo["fonte"] for modelo in MODELOS_LOTACAO.values())
    marcados.update({
        "%(total)s dia", "%(total)s dias", "%(total)s hora", "%(total)s horas",
        "já ocorreu hoje · com base em %(dias)s dias anteriores",
        "estimativa · com base em %(dias)s dias anteriores",
        "Tendência", "Conforto nas últimas 24h", "Tempo contínuo no status atual",
        "Maior nível atingido hoje", "Minutos em perigo / emergência hoje",
        "Horário previsto do pico", "Sensores indisponíveis", "Equipamentos ligados",
        "Geração %(id)s concluída: %(medicoes)s medição em %(zonas)s zona.",
        "Geração %(id)s concluída: %(medicoes)s medição em %(zonas)s zonas.",
        "Geração %(id)s concluída: %(medicoes)s medições em %(zonas)s zona.",
        "Geração %(id)s concluída: %(medicoes)s medições em %(zonas)s zonas.",
        "%(total)s nova medição copiada para o histórico.",
        "%(total)s novas medições copiadas para o histórico.",
        "%(total)s medição apagada do histórico.", "%(total)s medições apagadas do histórico.",
        "%(total)s medição gerada foi apagada.", "%(total)s medições geradas foram apagadas.",
        "Ainda não há leitura registrada para esta zona.",
        "A última leitura desta zona é antiga: o status térmico mostrado não é atual. Confira o coletor e os sensores.",
        "O índice ainda está subindo nos últimos 15 minutos: reforce o resfriamento.",
        "Tendência de subida nos últimos 15 minutos; monitore de perto.",
        "O índice já vem caindo nos últimos 15 minutos.",
        "%(total)s sensor sem leitura recente -- confira a conexão Modbus antes de confiar no índice mostrado.",
        "%(total)s sensores sem leitura recente -- confira a conexão Modbus antes de confiar no índice mostrado.",
        "%(equipamento)s ligado (intensidade %(intensidade)s, %(ativos)s de %(total)s ativos)",
        "%(equipamento)s ligado (%(ativos)s de %(total)s ativos)",
        "%(equipamento)s desligado, 0 de %(total)s ativos",
        "Ventilador", "Nebulizador", "Sensor",
        "Informe um valor numérico para %(campo)s.",
        "%(campo)s deve estar entre %(minimo)s e %(maximo)s.",
        "Selecione uma das cidades de referência da zona '%(zona)s'.",
        "Selecione uma categoria de densidade para a zona '%(zona)s'.",
        "A área útil da zona '%(zona)s' é insuficiente para um animal com o peso e a densidade selecionados.",
        "A lotação calculada da zona '%(zona)s' excede 1.000.000 de animais.",
        "Fuso horário inválido: %(fuso)s. Use um nome IANA, como America/Sao_Paulo.",
        "Produção de leite e ordenhas só se aplicam à zona bovina '%(zona)s'.",
        "Informe ao menos uma ordenha diária para a zona '%(zona)s'.",
        "Zona %(id)s não encontrada.", "Execução %(id)s não encontrada.",
    })
    assert marcados
    assert not {texto for texto in marcados if not catalogo.get(texto)}
    for original, traducao in catalogo.items():
        assert sorted(re.findall(r"%\([^)]+\)s", original)) == sorted(
            re.findall(r"%\([^)]+\)s", traducao)
        )


def test_idioma_isolado_e_normalizado():
    assert idioma.ativo() == "pt-br"
    token = idioma.ativar("en")
    try:
        assert idioma.ativo() == "en"
        outro = idioma.ativar("invalido")
        try:
            assert idioma.ativo() == "pt-br"
        finally:
            idioma.desativar(outro)
        assert idioma.ativo() == "en"
    finally:
        idioma.desativar(token)
    assert idioma.ativo() == "pt-br"


def test_recomendacoes_canonicas_sao_reconhecidas_no_navegador():
    script = (RAIZ / "app/static/js/core/i18n.js").read_text(encoding="utf-8")
    for mensagem in thermal_indices.MENSAGENS_STATUS.values():
        assert mensagem in script


def test_preferencia_do_navegador_respeita_prioridade():
    def escolher(cabecalho):
        return idioma.do_navegador(parse_accept_header(cabecalho, LanguageAccept))

    assert escolher("en-US,en;q=0.9,pt-BR;q=0.5") == "en"
    assert escolher("pt-BR,en;q=0.5") == "pt-br"
    assert escolher("fr-FR,fr;q=0.8") == "pt-br"
    assert escolher("en;q=0,pt;q=1") == "pt-br"


def test_login_no_idioma_do_navegador(client):
    resposta = client.get("/login", headers={"Accept-Language": "en-US"})
    html = resposta.get_data(as_text=True)
    assert '<html lang="en"' in html
    assert "Thermal Comfort" in html
    assert "Sign in to continue." in html
    assert "Password" in html
    resposta = client.get("/login", headers={"Accept-Language": "pt-BR"})
    html = resposta.get_data(as_text=True)
    assert '<html lang="pt-br"' in html
    assert "Entre com seu usuário para continuar." in html


def test_idioma_da_conta_prevalece_e_nao_vaza(app, client, monkeypatch):
    vistos = []

    @app.before_request
    def observar_idioma():
        vistos.append(idioma.ativo())

    client.get("/login", headers={"Accept-Language": "en-US"})
    assert vistos.pop() == "en"
    assert idioma.ativo() == "pt-br"

    usuario = {
        "id": 1, "nome": "Teste", "login": "teste", "perfil": "administrador",
        "ativo": True, "trocar_senha": False, "formato_regional": "br", "idioma": "pt-br",
    }
    monkeypatch.setattr(auth.db, "obter_usuario", lambda _id: usuario)
    monkeypatch.setattr(auth.db, "obter_hash_de_senha", lambda _id: "hash-de-teste")
    with client.session_transaction() as sessao:
        sessao["usuario_id"] = 1
        sessao[auth.CHAVE_MARCA_DE_SENHA] = marca_de_sessao(
            "hash-de-teste", chave_secreta=app.secret_key
        )
    client.get("/preferencias", headers={"Accept-Language": "en-US"})
    assert vistos.pop() == "pt-br"
    assert idioma.ativo() == "pt-br"


def test_troca_de_senha_traduz_orientacao_e_recusa(app, client, monkeypatch):
    usuario = {
        "id": 1, "nome": "Teste", "login": "teste", "perfil": "administrador",
        "ativo": True, "trocar_senha": False, "formato_regional": "br", "idioma": "en",
    }
    monkeypatch.setattr(auth.db, "obter_usuario", lambda _id: usuario)
    monkeypatch.setattr(auth.db, "obter_hash_de_senha", lambda _id: "hash-de-teste")
    monkeypatch.setattr(auth.db, "obter_usuario_por_login", lambda _login: None)
    app.config["WTF_CSRF_ENABLED"] = False
    with client.session_transaction() as sessao:
        sessao["usuario_id"] = 1
        sessao[auth.CHAVE_MARCA_DE_SENHA] = marca_de_sessao(
            "hash-de-teste", chave_secreta=app.secret_key
        )
    resposta = client.get("/minha-senha")
    assert '<html lang="en"' in resposta.get_data(as_text=True)
    assert "Current password" in resposta.get_data(as_text=True)
    resposta = client.post("/minha-senha", data={
        "senha_atual": "invalid", "senha_nova": "new", "senha_confirmacao": "new",
    })
    assert "Invalid current password." in resposta.get_data(as_text=True)


def test_preferencias_traduz_sem_mudar_o_formato_regional(app, client, monkeypatch):
    usuario = {
        "id": 1, "nome": "Teste", "login": "teste", "perfil": "administrador",
        "ativo": True, "trocar_senha": False, "formato_regional": "br", "idioma": "en",
    }
    monkeypatch.setattr(auth.db, "obter_usuario", lambda _id: usuario)
    monkeypatch.setattr(auth.db, "obter_hash_de_senha", lambda _id: "hash-de-teste")
    with client.session_transaction() as sessao:
        sessao["usuario_id"] = 1
        sessao[auth.CHAVE_MARCA_DE_SENHA] = marca_de_sessao(
            "hash-de-teste", chave_secreta=app.secret_key
        )
    html = client.get("/preferencias?salvo=1").get_data(as_text=True)
    assert '<html lang="en" data-regional="br"' in html
    assert "Preferences saved." in html
    assert "Date 31/12/2026 · Value 1.234,56" in html
    assert 'name="formato_regional" value="br"' in html


def test_preferencia_persistida_por_usuario(banco):
    usuarios = []
    try:
        for _ in range(2):
            usuarios.append(criar_usuario({
                "nome": "Teste", "login": uuid4().hex, "perfil": "administrador",
                "senha_hash": "hash-sintetico",
            }))
        primeiro, segundo = (usuario["id"] for usuario in usuarios)
        assert obter_usuario(primeiro)["idioma"] == "pt-br"
        assert atualizar_idioma(primeiro, "en") == "en"
        assert obter_usuario(primeiro)["idioma"] == "en"
        assert obter_usuario(segundo)["idioma"] == "pt-br"
        assert atualizar_idioma(primeiro, "invalido") == "pt-br"
        assert obter_usuario(primeiro)["idioma"] == "pt-br"
    finally:
        with banco() as conn:
            for usuario in usuarios:
                conn.execute("DELETE FROM usuarios WHERE id = ?", (usuario["id"],))
