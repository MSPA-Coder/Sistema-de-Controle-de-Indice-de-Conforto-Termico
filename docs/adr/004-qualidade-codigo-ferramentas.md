# ADR 004: ferramentas de qualidade na imagem dedicada

## Status

Aceito.

## Decisão

As dependências de execução ficam em `requirements.txt`. Ruff, Mypy, tipos e
Coverage ficam em `requirements-dev.txt`, instalados exclusivamente no estágio
Docker `quality`. A imagem `runtime` não contém testes nem ferramentas de
qualidade, e é a base dos serviços operacionais.

## Consequências

- Desenvolvimento e CI usam o serviço `test` de `compose.test.yaml`.
- A imagem operacional permanece menor e com superfície de dependências menor.
- Comandos de lint, tipagem, testes e cobertura são reproduzíveis sem Python
  instalado no host.
