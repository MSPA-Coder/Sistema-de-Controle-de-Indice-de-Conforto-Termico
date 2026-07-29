# ADR 003: Pipeline de CI/CD com GitHub Actions

## Status

Aceito

## Contexto

O sistema de Controle de Conforto Térmico Animal necessita de um processo automatizado para:

1. Validar mudanças de código antes da integração
2. Garantir que testes sejam executados consistentemente
3. Verificar qualidade de código e segurança
4. Construir imagens Docker para deploy

## Decisão

Implementar pipeline de CI/CD usando GitHub Actions com os seguintes jobs:

### Jobs do Pipeline

1. **Lint and Format**
   - Ruff para linting e formatação
   - Mypy para verificação de tipos (gradual)
   - Executa em todas as PRs e pushes

2. **Tests**
   - Unit tests com SQLite (rápido, sem dependências)
   - Integration tests com PostgreSQL (via Docker Compose)
   - Coverage report com fail-under=70%
   - Upload de artifacts para análise

3. **Security Scan**
   - pip-audit para vulnerabilidades em dependências
   - Detecta secrets acidentais no código

4. **Build Docker Images**
   - Build das imagens ICT e Coletor
   - Valida que Dockerfile funciona corretamente
   - Executa apenas se lint e tests passarem

## Configuração Técnica

- Python 3.13
- PostgreSQL 17 para testes de integração
- Cache de dependências pip para velocidade
- Parallel jobs para eficiência

## Consequências Positivas

- Feedback rápido para desenvolvedores
- Qualidade de código consistente
- Detecção precoce de bugs e vulnerabilidades
- Builds reprodutíveis
- Documentação implícita do processo de release

## Consequências Negativas

- Dependência de GitHub Actions (vendor lock-in parcial)
- Tempo de CI consome minutos gratuitos do GitHub
- Curva de aprendizado para equipe nova

## Alternativas Consideradas

1. **GitLab CI**: Boa alternativa, mas requeiria migração de repo
2. **Jenkins**: Mais flexível, mas maior complexidade operacional
3. **CircleCI**: Similar ao GitHub Actions, menos integração nativa

## Implementação

- Arquivo: `.github/workflows/ci.yml`
- Configurações adicionais:
  - `.pre-commit-config.yaml` para hooks locais
  - `ruff.toml` para configuração de linting
  - `mypy.ini` para configuração de type checking

## Referências

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [Ruff Documentation](https://docs.astral.sh/ruff/)
- [Mypy Documentation](https://mypy.readthedocs.io/)
