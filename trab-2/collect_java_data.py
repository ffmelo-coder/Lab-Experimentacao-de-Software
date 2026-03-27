#!/usr/bin/env python3
import os
import sys
import argparse
import subprocess
import json
import csv
import time
import shutil
import statistics
import tempfile

script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)

from github_utils import (
    fetch_repositories,
    validate_token,
    calculate_age_in_days,
    calculate_days_since_push,
    calculate_closed_issues_ratio,
)


def run_git_clone(clone_url, dest_dir, timeout=300):
    try:
        if os.path.exists(dest_dir):
            return True, "exists"
        os.makedirs(os.path.dirname(dest_dir), exist_ok=True)
        cmd = ["git", "clone", "--depth", "1", clone_url, dest_dir]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout)
        if proc.returncode == 0:
            return True, proc.stdout
        return False, proc.stderr
    except Exception as e:
        return False, str(e)


def run_cloc(repo_dir, cloc_cmd="cloc"):
    try:
        proc = subprocess.run([cloc_cmd, "--json", "--include-lang=Java", repo_dir], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if proc.returncode == 0 and proc.stdout:
            data = json.loads(proc.stdout)
            if "Java" in data:
                j = data["Java"]
                return j.get("code", 0), j.get("comment", 0), j.get("blank", 0)
        return None
    except FileNotFoundError:
        return None
    except Exception:
        return None


def count_java_loc(repo_dir):
    total = 0
    code = 0
    comments = 0
    blanks = 0
    for root, _, files in os.walk(repo_dir):
        for f in files:
            if f.endswith('.java'):
                path = os.path.join(root, f)
                try:
                    with open(path, 'r', encoding='utf-8', errors='ignore') as fh:
                        in_block = False
                        for line in fh:
                            total += 1
                            s = line.strip()
                            if not s:
                                blanks += 1
                                continue
                            if in_block:
                                comments += 1
                                if '*/' in s:
                                    in_block = False
                                continue
                            if s.startswith('//'):
                                comments += 1
                            elif s.startswith('/*'):
                                comments += 1
                                if '*/' not in s:
                                    in_block = True
                            else:
                                code += 1
                except Exception:
                    continue
    return code, comments, blanks


def run_ck_for_repo(repo_dir, ck_cmd_template, timeout=300):
    # ck_cmd_template must include placeholders {repo_dir} and {out_dir}
    out_dir = tempfile.mkdtemp(prefix='ck_out_')
    cmd = ck_cmd_template.format(repo_dir=repo_dir, out_dir=out_dir)
    try:
        proc = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout)
        # ignore return code; parse outputs in out_dir
        metrics = parse_ck_output(out_dir)
        return metrics
    except Exception as e:
        print(f"Erro executando CK: {e}")
        return None
    finally:
        try:
            shutil.rmtree(out_dir)
        except Exception:
            pass


def parse_ck_output(out_dir):
    # procura por CSV ou JSON na pasta de saída
    for root, _, files in os.walk(out_dir):
        for f in files:
            path = os.path.join(root, f)
            if f.lower().endswith('.json'):
                try:
                    with open(path, 'r', encoding='utf-8') as fh:
                        data = json.load(fh)
                        # procurar por lista de classes com métricas
                        # estrutura pode variar entre implementações; tentamos heurísticas
                        values = []
                        if isinstance(data, list):
                            for item in data:
                                if isinstance(item, dict):
                                    values.append(item)
                        elif isinstance(data, dict):
                            # procurar por chave com lista
                            for v in data.values():
                                if isinstance(v, list):
                                    values = v
                                    break

                        if not values:
                            continue

                        cbo_list = []
                        dit_list = []
                        lcom_list = []
                        for cls in values:
                            if not isinstance(cls, dict):
                                continue
                            # chaves heurísticas
                            for k in cls.keys():
                                lk = k.lower()
                            # tentar extrair campos
                            def getf(d, keys):
                                for k in keys:
                                    if k in d:
                                        try:
                                            return float(d[k])
                                        except:
                                            try:
                                                return float(d[k].replace(',', '.'))
                                            except:
                                                pass
                                return None

                            cbo = getf(cls, ['cbo', 'coupling'])
                            dit = getf(cls, ['dit', 'depthInInheritanceTree', 'depth'])
                            lcom = getf(cls, ['lcom', 'lcom4', 'lackOfCohesion'])
                            if cbo is not None:
                                cbo_list.append(cbo)
                            if dit is not None:
                                dit_list.append(dit)
                            if lcom is not None:
                                lcom_list.append(lcom)

                        result = {}
                        if cbo_list:
                            result['cbo_mean'] = statistics.mean(cbo_list)
                            result['cbo_median'] = statistics.median(cbo_list)
                        if dit_list:
                            result['dit_mean'] = statistics.mean(dit_list)
                            result['dit_median'] = statistics.median(dit_list)
                        if lcom_list:
                            result['lcom_mean'] = statistics.mean(lcom_list)
                            result['lcom_median'] = statistics.median(lcom_list)

                        return result
                except Exception:
                    continue

            if f.lower().endswith('.csv'):
                try:
                    with open(path, 'r', encoding='utf-8', errors='ignore') as fh:
                        reader = csv.DictReader(fh)
                        cbo_list = []
                        dit_list = []
                        lcom_list = []
                        for row in reader:
                            # localizar chaves CBO, DIT, LCOM (case-insensitive)
                            lower_map = {k.lower(): v for k, v in row.items()}
                            def get_from_map(m, names):
                                for n in names:
                                    if n in m and m[n] not in (None, ''):
                                        try:
                                            return float(m[n])
                                        except:
                                            try:
                                                return float(m[n].replace(',', '.'))
                                            except:
                                                pass
                                return None

                            cbo = get_from_map(lower_map, ['cbo'])
                            dit = get_from_map(lower_map, ['dit'])
                            lcom = get_from_map(lower_map, ['lcom'])
                            if cbo is not None:
                                cbo_list.append(cbo)
                            if dit is not None:
                                dit_list.append(dit)
                            if lcom is not None:
                                lcom_list.append(lcom)

                        result = {}
                        if cbo_list:
                            result['cbo_mean'] = statistics.mean(cbo_list)
                            result['cbo_median'] = statistics.median(cbo_list)
                        if dit_list:
                            result['dit_mean'] = statistics.mean(dit_list)
                            result['dit_median'] = statistics.median(dit_list)
                        if lcom_list:
                            result['lcom_mean'] = statistics.mean(lcom_list)
                            result['lcom_median'] = statistics.median(lcom_list)
                        return result
                except Exception:
                    continue

    return None


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
