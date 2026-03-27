# Estudo de Qualidade de Repositórios Java

Este diretório contém uma adaptação do coletor do trabalho anterior para focar em repositórios escritos em Java e preparar a extração de métricas de produto (CBO, DIT, LCOM) via ferramenta CK.

Arquivos principais
- `github_utils.py`: utilitários para consulta GraphQL ao GitHub (filtrando `language:Java`).
- `collect_java_data.py`: script principal que coleta os top repositórios Java, clona-os (opcional), obtém LOC (via `cloc` ou fallback) e integra execução opcional da ferramenta CK.

Requisitos
- Python 3.8+
- Pacote Python `requests` (pip install requests)
- `git` no PATH
- `cloc` (opcional, recomendado) — para contagem precisa de LOC/comentários. Se não disponível, o script usa um contador simples para arquivos `.java`.
- Java + `ck` (jar) — para calcular métricas CBO/DIT/LCOM via CK (opcional). O `ck` não é incluído aqui; baixe o jar da ferramenta CK e forneça um comando via `--ck-cmd`.

Observações importantes
- O script fará muitos clones (até 1000 por padrão). Isso demanda espaço em disco e tempo — use o argumento `--max` para limitar a coleta em testes.
- Forneça um token GitHub com permissões públicas via `--token` ou pela variável de ambiente `GITHUB_TOKEN`.

Exemplos de uso

1) Teste rápido, sem clonar:

```
python collect_java_data.py --token YOUR_TOKEN --max 20 --skip-clone --output sample_java.csv
```

2) Coleta com clonagem + uso do `cloc` (se instalado):

```
python collect_java_data.py --token YOUR_TOKEN --max 200 --output java_metrics.csv
```

3) Integrando a execução do CK (exemplo genérico):

O `--ck-cmd` deve ser um comando shell que contenha os placeholders `{repo_dir}` e `{out_dir}`.
Por exemplo, se você tiver o jar `ck.jar` que aceita um diretório de saída, pode usar algo como:

```
python collect_java_data.py --token YOUR_TOKEN --max 100 --ck-cmd "java -jar /path/to/ck.jar {repo_dir} {out_dir}" --output java_with_ck.csv
```

Dependendo da versão do CK que você baixar, os parâmetros podem variar. Ajuste `--ck-cmd` conforme a documentação do jar que você estiver utilizando.

Saída
- Um CSV com colunas de processo (estrelas, idade, releases, issues, etc.) e colunas para métricas de produto quando disponível (`CBO_Mean`, `CBO_Median`, `DIT_Mean`, `DIT_Median`, `LCOM_Mean`, `LCOM_Median`).

Próximos passos sugeridos
- Se desejar, posso tentar integrar uma implementação em Python para estimar DIT/CBO/LCOM sem precisar do CK (mais impreciso, mas útil para testes rápidos).
