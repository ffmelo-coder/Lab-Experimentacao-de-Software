#!/usr/bin/env python3
import os
import sys
import stat
import shutil
import argparse
import time

def _remove_readonly(func, path, _exc):
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception:
        pass


def remove_dir(path):
    if not os.path.exists(path):
        return
    import subprocess

    result = subprocess.run(
        ["cmd", "/c", "rd", "/s", "/q", os.path.abspath(path)], capture_output=True
    )
    if result.returncode != 0 or os.path.exists(path):
        # aguarda 2s e tenta shutil
        time.sleep(2)
        shutil.rmtree(path, onexc=_remove_readonly)

script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)

# Token do GitHub
GITHUB_TOKEN = "seu_token_aqui"

# Caminho para o JAR do CK
_ck_jar = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "ck",
    "ck-0.7.1-SNAPSHOT-jar-with-dependencies.jar",
)
CK_CMD = f'java -jar "{_ck_jar}" {{repo_dir}} true 0 false {{out_dir}}'

from github_utils import (
    fetch_repositories,
    validate_token,
    calculate_age_in_days,
    calculate_days_since_push,
    calculate_closed_issues_ratio,
    format_age,
    run_git_clone,
    run_cloc,
    count_java_loc,
    run_ck_for_repo,
    write_list_csv,
    write_results_csv,
)


def display_repository_data(repos, start_index):
    print("\n" + "=" * 85)
    print(
        f"{'#':<5} {'Repositório':<40} {'Estrelas':<12} {'Idade':<20} {'Releases':<8}"
    )
    print("=" * 85)

    for i, repo in enumerate(repos, start=start_index + 1):
        node = repo["node"]
        name = f"{node['owner']['login']}/{node['name']}"
        stars = node.get("stargazerCount", 0)
        age_formatted = format_age(calculate_age_in_days(node["createdAt"]))
        releases = node["releases"]["totalCount"]

        if len(name) > 38:
            name = name[:35] + "..."

        print(f"{i:<5} {name:<40} {stars:<12} {age_formatted:<20} {releases:<8}")

    print("=" * 85)

def write_results_csv(rows, filename):
    header = [
        'Repositório', 'Owner', 'Nome', 'Estrelas', 'Linguagem Primária',
        'Data Criação', 'Idade (dias)', 'Data Último Push', 'Dias desde Último Push',
        'PRs Aceitas', 'Releases', 'Total Issues', 'Issues Fechadas', '% Issues Fechadas',
        'LOC Java', 'Comments Java', 'Blank Java',
        'CBO_Mean', 'CBO_Median', 'DIT_Mean', 'DIT_Median', 'LCOM_Mean', 'LCOM_Median'
    ]

    with open(filename, 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f)
        w.writerow(header)
        for r in rows:
            w.writerow([
                r.get('full_name'), r.get('owner'), r.get('name'), r.get('stars'), r.get('language'),
                r.get('createdAt'), r.get('age_days'), r.get('pushedAt'), r.get('days_since_push'),
                r.get('pr_count'), r.get('release_count'), r.get('total_issues'), r.get('closed_issues'), r.get('pct_issues'),
                r.get('loc_java'), r.get('comments_java'), r.get('blank_java'),
                r.get('cbo_mean'), r.get('cbo_median'), r.get('dit_mean'), r.get('dit_median'), r.get('lcom_mean'), r.get('lcom_median')
            ])


def main():
    parser = argparse.ArgumentParser(description='Coletor de métricas para repositórios Java (top por estrelas)')
    parser.add_argument('--token', help='GitHub token (ou use variável de ambiente GITHUB_TOKEN)')
    parser.add_argument('--max', type=int, default=1000, help='Número máximo de repositórios a coletar')
    parser.add_argument('--per-page', type=int, default=100, help='Itens por página (max 100)')
    parser.add_argument('--repos-dir', default='repos', help='Diretório para clonar repositórios')
    parser.add_argument('--output', default='java_repos_metrics.csv', help='Arquivo CSV de saída')
    parser.add_argument('--ck-cmd', default=None, help='Comando para executar CK, use {repo_dir} e {out_dir} como placeholders')
    parser.add_argument('--skip-clone', action='store_true', help='Não clona repositórios (útil para teste)')
    args = parser.parse_args()

    token = args.token or os.environ.get('GITHUB_TOKEN')
    if not token:
        print('Forneça um token via --token ou variavel de ambiente GITHUB_TOKEN')
        return

    if not validate_token(token):
        print('Token inválido ou sem permissão. Verifique.')
        return

    os.makedirs(args.repos_dir, exist_ok=True)

    all_repos = []
    cursor = None
    total_fetched = 0

    print(f'Coletando até {args.max} repositórios Java (página {args.per_page})...')

    while total_fetched < args.max:
        print(f'Buscando página {(total_fetched // args.per_page) + 1}...')
        data = fetch_repositories(token, cursor, args.per_page)
        if not data or 'data' not in data:
            print('Erro ao buscar dados ou limite de requisições atingido')
            break
        if 'errors' in data:
            print('Erro na query GraphQL:', data['errors'])
            break

        search_data = data['data']['search']
        edges = search_data['edges']
        if not edges:
            break

        all_repos.extend(edges)
        total_fetched += len(edges)
        page_info = search_data.get('pageInfo', {})
        if not page_info.get('hasNextPage') or total_fetched >= args.max:
            break
        cursor = page_info.get('endCursor')
        time.sleep(1)

    print(f'Total coletado: {len(all_repos)}')

    results = []
    for i, edge in enumerate(all_repos[:args.max], start=1):
        node = edge['node']
        owner = node['owner']['login']
        name = node['name']
        full_name = f"{owner}/{name}"
        print(f'[{i}] Processando {full_name}...')

        stars = node.get('stargazerCount', 0)
        createdAt = node.get('createdAt')
        age_days = calculate_age_in_days(createdAt) if createdAt else None
        pushedAt = node.get('pushedAt')
        days_since = calculate_days_since_push(pushedAt) if pushedAt else None
        pr_count = node.get('pullRequests', {}).get('totalCount', 0)
        release_count = node.get('releases', {}).get('totalCount', 0)
        total_issues = node.get('issues', {}).get('totalCount', 0)
        closed_issues = node.get('closedIssues', {}).get('totalCount', 0)
        pct_issues = calculate_closed_issues_ratio(closed_issues, total_issues)
        language = node.get('primaryLanguage', {}).get('name') if node.get('primaryLanguage') else 'Java'

        repo_clone_dir = os.path.join(args.repos_dir, f"{owner}__{name}")
        loc_java = comments_java = blank_java = None
        if not args.skip_clone:
            clone_url = f"https://github.com/{owner}/{name}.git"
            ok, msg = run_git_clone(clone_url, repo_clone_dir)
            if not ok:
                print(f"  Falha ao clonar: {msg}")
            else:
                cloc_res = run_cloc(repo_clone_dir)
                if cloc_res:
                    loc_java, comments_java, blank_java = cloc_res
                else:
                    loc_java, comments_java, blank_java = count_java_loc(repo_clone_dir)

        ck_metrics = None
        if args.ck_cmd and (not args.skip_clone):
            ck_metrics = run_ck_for_repo(repo_clone_dir, args.ck_cmd)

        row = {
            'full_name': full_name,
            'owner': owner,
            'name': name,
            'stars': stars,
            'language': language,
            'createdAt': createdAt,
            'age_days': age_days,
            'pushedAt': pushedAt,
            'days_since_push': days_since,
            'pr_count': pr_count,
            'release_count': release_count,
            'total_issues': total_issues,
            'closed_issues': closed_issues,
            'pct_issues': f"{pct_issues:.2f}",
            'loc_java': loc_java,
            'comments_java': comments_java,
            'blank_java': blank_java,
        }

        if ck_metrics:
            row.update(ck_metrics)

        results.append(row)

    print(f'Gravando resultados em {args.output} ...')
    write_results_csv(results, args.output)
    print('Concluído.')


if __name__ == '__main__':
    main()
