# Análise de Qualidade de Repositórios Java Populares

Sistema desenvolvido para o Laboratório de Experimentação de Software - PUCMINAS 01/2026

## Visão Geral

Este projeto estende o coletor do Trabalho 1 para focar nos 1000 repositórios Java mais populares do GitHub, combinando métricas de processo (popularidade, maturidade, atividade, tamanho) com métricas de produto de qualidade de código (CBO, DIT, LCOM) extraídas via ferramenta CK.

## Questões de Pesquisa

O sistema coleta dados para responder as seguintes questões:

- **RQ01**: Qual a relação entre a popularidade dos repositórios e as suas características de qualidade?
- **RQ02**: Qual a relação entre a maturidade dos repositórios e as suas características de qualidade?
- **RQ03**: Qual a relação entre a atividade dos repositórios e as suas características de qualidade?
- **RQ04**: Qual a relação entre o tamanho dos repositórios e as suas características de qualidade?

As características de qualidade analisadas são as métricas extraídas pela ferramenta CK: **CBO** (acoplamento entre objetos), **DIT** (profundidade de herança) e **LCOM** (falta de coesão dos métodos).

## Arquitetura do Sistema

### Módulos

```
trab-2/
├── github_utils.py              # Módulo compartilhado com funções reutilizáveis
├── collect_java_data.py         # Interface CLI (linha de comando)
├── ck/
│   └── ck-0.7.1-SNAPSHOT-jar-with-dependencies.jar  # Ferramenta CK
└── README.md                    # Este arquivo
```

### Módulo Compartilhado (github_utils.py)

Centraliza toda a lógica de coleta e análise:

**Funções principais:**

- `fetch_repositories()` — Requisições GraphQL com filtro `language:Java`
- `run_git_clone()` — Sparse checkout (apenas `.java`) com suporte a caminhos longos
- `count_java_loc()` — Contagem de linhas de código Java
- `run_ck_for_repo()` — Executa o CK e extrai médias/medianas de CBO, DIT e LCOM
- `calculate_age_in_days()` — Calcula idade do repositório
- `calculate_days_since_push()` — Dias desde último commit
- `calculate_closed_issues_ratio()` — Percentual de issues fechadas
- `validate_token()` — Valida token do GitHub
- `write_results_csv()` — Exporta métricas de processo e produto para CSV
- `write_list_csv()` — Exporta lista de repositórios sem métricas CK

**Configurações:**

- GraphQL query filtrada para `language:Java`
- Sparse checkout: baixa apenas arquivos `.java` (evita nomes longos no Windows)
- Timeout configurado: 10s (connect) + 30s (read)
- Retry automático: 3 tentativas com backoff exponencial

## Instalação e Requisitos

### Dependências

```bash
pip install requests
```

**Ferramentas externas:**

- `git` no PATH — para clonagem dos repositórios
- `java` no PATH — para execução do CK

O JAR do CK (`ck-0.7.1-SNAPSHOT-jar-with-dependencies.jar`) já está incluído na pasta `ck/`.

### Token do GitHub

1. Acesse https://github.com/settings/tokens
2. Clique em "Generate new token (classic)"
3. Selecione permissão `public_repo`
4. Copie o token e insira no topo de `collect_java_data.py`:

```python
GITHUB_TOKEN = "seu_token_aqui"
```

## Como Usar

### Interface CLI (Linha de Comando)

```bash
python collect_java_data.py
```

**Argumentos disponíveis:**

| Argumento      | Padrão                   | Descrição                                                     |
| -------------- | ------------------------ | ------------------------------------------------------------- |
| `--max`        | 1000                     | Número máximo de repositórios                                 |
| `--per-page`   | 10                       | Itens por página (máx. 100)                                   |
| `--repos-dir`  | `repos`                  | Diretório para clones temporários                             |
| `--output`     | `java_repos_metrics.csv` | Arquivo CSV de saída                                          |
| `--skip-clone` | —                        | Não clona (útil para testes)                                  |
| `--list-only`  | —                        | Apenas lista repos, sem CK, salva em `java_top1000_repos.csv` |

**Exemplos de uso:**

1. Teste rápido sem clonar:

```bash
python collect_java_data.py --max 20 --skip-clone --output sample.csv
```

2. Coleta parcial com métricas CK:

```bash
python collect_java_data.py --max 100 --output java_metrics.csv
```

3. Apenas listar repositórios (sem CK):

```bash
python collect_java_data.py --max 1000 --list-only
```

**Funcionamento:**

- Coleta repositórios Java por paginação GraphQL com deduplicação
- Exibe tabela em tempo real com: repositório, estrelas, idade e releases
- Para cada repo: faz sparse checkout (só `.java`), executa CK, depois remove o clone
- Grava resultados no CSV ao final

## Formato de Dados Coletados

### Dados por Repositório

**Métricas de processo:**

1. `full_name` — owner/name
2. `owner` — dono do repositório
3. `name` — nome do repositório
4. `stars` — número de estrelas (popularidade)
5. `language` — linguagem primária
6. `createdAt` — data de criação
7. `age_days` — idade em dias (maturidade)
8. `pushedAt` — data do último push
9. `days_since_push` — dias desde o último push (atividade)
10. `pr_count` — total de pull requests (atividade)
11. `release_count` — total de releases (atividade)
12. `total_issues` — total de issues
13. `closed_issues` — issues fechadas
14. `pct_issues` — percentual de issues fechadas
15. `loc_java` — linhas de código Java (tamanho)
16. `comments_java` — linhas de comentário Java
17. `blank_java` — linhas em branco Java

**Métricas de produto — CK (características de qualidade):**

18. `CBO_Mean` / `CBO_Median` — Coupling Between Objects (acoplamento entre objetos)
19. `DIT_Mean` / `DIT_Median` — Depth of Inheritance Tree (profundidade de herança)
20. `LCOM_Mean` / `LCOM_Median` — Lack of Cohesion of Methods (falta de coesão)

- **CBO** _(Coupling Between Objects)_ — Acoplamento entre objetos: conta quantas outras classes uma classe utiliza diretamente. Valores altos indicam forte dependência entre componentes, tornando o código mais difícil de testar, manter e reutilizar.

- **DIT** _(Depth of Inheritance Tree)_ — Profundidade de herança: mede quantos níveis de herança uma classe possui na hierarquia. Valores altos indicam maior reuso via herança, mas também maior complexidade e risco de efeitos colaterais entre classes pai e filho.

- **LCOM** _(Lack of Cohesion of Methods)_ — Falta de coesão dos métodos: mede o quanto os métodos de uma classe compartilham os mesmos atributos internos. Valores altos indicam que a classe provavelmente faz coisas demais e deveria ser dividida em classes menores e mais focadas.

## Detalhes Técnicos

### API do GitHub

**Requisições:**

- GraphQL API v4 com filtro `language:Java`
- Paginação: 10 itens por requisição
- Deduplicação por nome completo entre páginas
- Repaginação automática quando a página esgota (filtra por `stars:<min`)
- Rate limiting: 1 segundo entre requisições

### Estratégia de Clone

O script usa **sparse checkout** em vez de clone completo:

```
git clone --depth 1 --filter=blob:none --sparse  (metadados apenas)
git sparse-checkout set --no-cone **/*.java       (configura filtro)
git checkout                                      (baixa só os .java)
```

**Vantagens:**

- Evita erros de `Filename too long` no Windows (ex.: spring-boot)
- Reduz drasticamente o uso de disco e tempo de clonagem
- LOC e CK analisam exatamente o mesmo conjunto de arquivos

### Ferramenta CK

O CK analisa os arquivos `.java` e gera arquivos CSV com métricas por classe. O script:

1. Executa: `java -jar ck.jar {repo_dir} true 0 false {out_dir}`
2. Lê `class.csv` do diretório de saída
3. Calcula média e mediana de CBO, DIT e LCOM por repositório
4. Remove o clone e os arquivos temporários do CK

### Tratamento de Erros

**Retry Automático:**

- 3 tentativas em caso de falha na API
- Backoff exponencial: 1s → 2s → 4s

**Remoção de diretórios no Windows:**

- Usa `rd /s /q` (comando nativo) para lidar com arquivos bloqueados pelo antivírus
- Fallback para `shutil.rmtree` com handler de permissão se necessário

**Tipos de Erro Tratados:**

- Timeout de conexão
- Erros de rede
- Token inválido
- Rate limiting
- Erros GraphQL
- Falha no clone (repositório ignorado, coleta continua)
- Falha no CK (métricas ficam em branco, demais dados são salvos)

## Resolução de Problemas

### Filename too long (Windows)

**Sintoma:** `error: unable to create file ... Filename too long` durante o clone

**Causa:** Windows tem limite de 260 caracteres no caminho.

**Solução aplicada:** O script já usa `core.longpaths=true` + sparse checkout. Se ainda ocorrer, habilite manualmente:

```powershell
git config --global core.longpaths true
```

### Arquivo bloqueado ao deletar

**Sintoma:** `PermissionError: [WinError 32] O arquivo já está sendo usado por outro processo`

**Causa:** Windows Defender ou indexador escaneia os arquivos recém-clonados.

**Solução aplicada:** O script usa `rd /s /q` nativo.

### Token Inválido

**Sintoma:** `Token inválido ou sem permissão.`

**Soluções:**

- Confirmar que o token começa com `ghp_` ou `github_pat_`
- Confirmar permissão `public_repo`
- Gerar novo token se expirado

### CK não gera saída

**Sintoma:** Colunas CBO/DIT/LCOM ficam vazias no CSV

**Causas e soluções:**

- Java não está no PATH: verifique com `java -version`
- Nenhum `.java` encontrado no repositório: sparse checkout sem arquivos
- Versão do CK incompatível: o jar incluído é `0.7.1-SNAPSHOT`

## Performance

**Tempo estimado (1000 repositórios):**

- Coleta GraphQL: ~17min (1000 requisições × 1s de delay)
- Clone + CK por repo: 30s a 5min dependendo do tamanho
- Total: várias horas para coleta completa

**Uso de disco:**

- Clones são temporários e removidos após cada repositório
- Espaço máximo simultâneo: tamanho do maior repositório clonado

**Dica:** Use `--max 10` para validar o pipeline antes de rodar os 1000.

## Limitações Conhecidas

1. **Apenas arquivos `.java`:** O sparse checkout exclui outros tipos — LOC de outras linguagens não é contabilizada
2. **Rate Limiting:** GitHub limita requisições à API — delay de 1s já está configurado
3. **Repositórios sem Java real:** Repos que declaram Java como linguagem primária mas têm poucos `.java` terão métricas CK imprecisas
4. **CK em projetos muito grandes:** Pode demorar vários minutos por repositório (ex.: elasticsearch, spring-boot)

## Licença

Projeto acadêmico - PUCMINAS 2026

## Autores

Augusto Fuscaldi Cerezo

Filipe Faria Melo

Desenvolvido para a disciplina de Experimentação de Software
