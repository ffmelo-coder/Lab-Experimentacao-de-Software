import requests
import time
import csv
from datetime import datetime


GITHUB_API_URL = "https://api.github.com/graphql"

GRAPHQL_QUERY = """
query ($cursor: String, $pageSize: Int!) {
  search(query: "stars:>1", type: REPOSITORY, first: $pageSize, after: $cursor) {
    repositoryCount
    pageInfo {
      endCursor
      hasNextPage
    }
    edges {
      node {
        ... on Repository {
          name
          owner {
            login
          }
          createdAt
          updatedAt
          pushedAt
          stargazerCount
          primaryLanguage {
            name
          }
          pullRequests(states: MERGED) {
            totalCount
          }
          releases {
            totalCount
          }
          issues {
            totalCount
          }
          closedIssues: issues(states: CLOSED) {
            totalCount
          }
        }
      }
    }
  }
}
"""


def calculate_age_in_days(created_at):
    created_date = datetime.strptime(created_at, "%Y-%m-%dT%H:%M:%SZ")
    current_date = datetime.now()
    age = (current_date - created_date).days
    return age


def format_age(days):
    years = days // 365
    remaining_days = days % 365
    if years > 0:
        return f"{years} anos e {remaining_days} dias"
    return f"{days} dias"


def calculate_days_since_update(updated_at):
    try:
        updated_date = datetime.strptime(updated_at, "%Y-%m-%dT%H:%M:%SZ")
        current_date = datetime.now()
        days_since = (current_date - updated_date).days
        return max(0, days_since)
    except Exception as e:
        print(f"Erro ao calcular dias desde atualização: {e}, data: {updated_at}")
        return 0


def calculate_days_since_push(pushed_at):
    try:
        if not pushed_at:
            return -1
        pushed_date = datetime.strptime(pushed_at, "%Y-%m-%dT%H:%M:%SZ")
        current_date = datetime.now()
        days_since = (current_date - pushed_date).days
        return max(0, days_since)
    except Exception as e:
        print(f"Erro ao calcular dias desde push: {e}, data: {pushed_at}")
        return -1


def calculate_closed_issues_ratio(closed, total):
    if total == 0:
        return 0.0
    return (closed / total) * 100


def fetch_repositories(token, cursor=None, page_size=10, retries=3):
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    variables = {"cursor": cursor, "pageSize": page_size}
    payload = {"query": GRAPHQL_QUERY, "variables": variables}

    for attempt in range(retries):
        try:
            # timeout de 30 segundos
            response = requests.post(
                GITHUB_API_URL,
                headers=headers,
                json=payload,
                timeout=(10, 30),  # (connect timeout, read timeout)
            )
            response.raise_for_status()
            return response.json()

        except requests.exceptions.Timeout as e:
            if attempt < retries - 1:
                wait_time = 2**attempt
                print(
                    f"⚠️ Timeout na tentativa {attempt + 1}. Aguardando {wait_time}s antes de tentar novamente..."
                )
                time.sleep(wait_time)
            else:
                print(
                    f"❌ Erro: Timeout após {retries} tentativas. Verifique sua conexão com internet."
                )
                return None

        except requests.exceptions.RequestException as e:
            if attempt < retries - 1:
                print(f"⚠️ Erro na tentativa {attempt + 1}: {e}. Tentando novamente...")
                time.sleep(2)
            else:
                print(f"❌ Erro na requisição após {retries} tentativas: {e}")
                return None

    return None


def validate_token(token):
    test_query = """
    query {
      viewer {
        login
      }
    }
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {"query": test_query}

    try:
        response = requests.post(
            GITHUB_API_URL, headers=headers, json=payload, timeout=10
        )
        data = response.json()
        if "errors" in data:
            return False
        return True
    except:
        return False


def export_to_csv(all_repos, filename):

    if not all_repos:
        return False

    try:
        with open(filename, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)

            writer.writerow(
                [
                    "Repositório",
                    "Owner",
                    "Nome",
                    "Estrelas",
                    "Linguagem Primária",
                    "Data Criação",
                    "Idade (dias)",
                    "Data Último Push",
                    "Dias desde Último Push",
                    "PRs Aceitas",
                    "Releases",
                    "Total Issues",
                    "Issues Fechadas",
                    "% Issues Fechadas",
                ]
            )

            for repo in all_repos:
                node = repo["node"]
                full_name = f"{node['owner']['login']}/{node['name']}"
                age_days = calculate_age_in_days(node["createdAt"])
                days_since = calculate_days_since_push(node["pushedAt"])
                language = (
                    node["primaryLanguage"]["name"]
                    if node["primaryLanguage"]
                    else "N/A"
                )
                total_issues = node["issues"]["totalCount"]
                closed_issues = node["closedIssues"]["totalCount"]
                issues_ratio = calculate_closed_issues_ratio(
                    closed_issues, total_issues
                )

                writer.writerow(
                    [
                        full_name,
                        node["owner"]["login"],
                        node["name"],
                        node["stargazerCount"],
                        language,
                        node["createdAt"],
                        age_days,
                        node["pushedAt"],
                        days_since,
                        node["pullRequests"]["totalCount"],
                        node["releases"]["totalCount"],
                        total_issues,
                        closed_issues,
                        f"{issues_ratio:.2f}",
                    ]
                )

            writer.writerow([])
            writer.writerow(["ESTATÍSTICAS GERAIS - ANÁLISE DOS REPOSITÓRIOS"])
            writer.writerow([])

            ages = [
                calculate_age_in_days(repo["node"]["createdAt"]) for repo in all_repos
            ]
            pr_counts = [
                repo["node"]["pullRequests"]["totalCount"] for repo in all_repos
            ]
            release_counts = [
                repo["node"]["releases"]["totalCount"] for repo in all_repos
            ]
            days_since_push_list = [
                calculate_days_since_push(repo["node"]["pushedAt"])
                for repo in all_repos
            ]

            issues_ratios = []
            for repo in all_repos:
                node = repo["node"]
                total = node["issues"]["totalCount"]
                closed = node["closedIssues"]["totalCount"]
                issues_ratios.append(calculate_closed_issues_ratio(closed, total))

            # RQ01
            writer.writerow(["RQ01 - Sistemas populares são maduros/antigos?"])
            writer.writerow(["Média de Idade (dias)", sum(ages) // len(ages)])
            writer.writerow(["Mediana de Idade (dias)", sorted(ages)[len(ages) // 2]])
            writer.writerow(["Idade Mínima (dias)", min(ages)])
            writer.writerow(["Idade Máxima (dias)", max(ages)])
            writer.writerow([])

            # RQ02
            writer.writerow(
                ["RQ02 - Sistemas populares recebem muita contribuição externa?"]
            )
            writer.writerow(["Média de PRs Aceitas", sum(pr_counts) // len(pr_counts)])
            writer.writerow(["Mediana de PRs", sorted(pr_counts)[len(pr_counts) // 2]])
            writer.writerow(["Mínimo de PRs", min(pr_counts)])
            writer.writerow(["Máximo de PRs", max(pr_counts)])
            writer.writerow([])

            # RQ03
            writer.writerow(
                ["RQ03 - Sistemas populares lançam releases com frequência?"]
            )
            writer.writerow(
                ["Média de Releases", sum(release_counts) // len(release_counts)]
            )
            writer.writerow(
                [
                    "Mediana de Releases",
                    sorted(release_counts)[len(release_counts) // 2],
                ]
            )
            writer.writerow(["Mínimo de Releases", min(release_counts)])
            writer.writerow(["Máximo de Releases", max(release_counts)])
            writer.writerow([])

            # RQ04
            writer.writerow(
                ["RQ04 - Sistemas populares são atualizados com frequência?"]
            )
            writer.writerow(
                [
                    "Média de dias desde último push",
                    sum(days_since_push_list) // len(days_since_push_list),
                ]
            )
            writer.writerow(
                [
                    "Mediana (dias)",
                    sorted(days_since_push_list)[len(days_since_push_list) // 2],
                ]
            )
            writer.writerow(["Mínimo (dias)", min(days_since_push_list)])
            writer.writerow(["Máximo (dias)", max(days_since_push_list)])
            writer.writerow([])

            # RQ05
            writer.writerow(
                [
                    "RQ05 - Sistemas populares são escritos nas linguagens mais populares?"
                ]
            )
            language_count = {}
            for repo in all_repos:
                lang = repo["node"]["primaryLanguage"]
                lang_name = lang["name"] if lang else "N/A"
                language_count[lang_name] = language_count.get(lang_name, 0) + 1

            sorted_languages = sorted(
                language_count.items(), key=lambda x: x[1], reverse=True
            )
            writer.writerow(["Top 10 Linguagens", "Repositórios", "Percentual"])
            for lang, count in sorted_languages[:10]:
                percentage = (count / len(all_repos)) * 100
                writer.writerow([lang, count, f"{percentage:.1f}%"])
            writer.writerow([])

            # RQ06
            writer.writerow(
                [
                    "RQ06 - Sistemas populares possuem alto percentual de issues fechadas?"
                ]
            )
            avg_ratio = sum(issues_ratios) / len(issues_ratios)
            writer.writerow(["Média de Issues Fechadas (%)", f"{avg_ratio:.2f}"])
            writer.writerow(
                ["Mediana (%)", f"{sorted(issues_ratios)[len(issues_ratios)//2]:.2f}"]
            )
            writer.writerow(["Mínimo (%)", f"{min(issues_ratios):.2f}"])
            writer.writerow(["Máximo (%)", f"{max(issues_ratios):.2f}"])
            writer.writerow([])

            # RQ07
            writer.writerow(["RQ07 - Análise por Linguagem (Top 5)"])
            writer.writerow([])
            for lang, count in sorted_languages[:5]:
                repos_lang = [
                    r
                    for r in all_repos
                    if (
                        r["node"]["primaryLanguage"]
                        and r["node"]["primaryLanguage"]["name"] == lang
                    )
                    or (not r["node"]["primaryLanguage"] and lang == "N/A")
                ]

                if repos_lang:
                    prs = [r["node"]["pullRequests"]["totalCount"] for r in repos_lang]
                    releases = [r["node"]["releases"]["totalCount"] for r in repos_lang]
                    pushes = [
                        calculate_days_since_push(r["node"]["pushedAt"])
                        for r in repos_lang
                    ]

                    writer.writerow([f"{lang} ({count} repositórios)"])
                    writer.writerow(["Média PRs", sum(prs) // len(prs)])
                    writer.writerow(["Mediana PRs", sorted(prs)[len(prs) // 2]])
                    writer.writerow(["Média Releases", sum(releases) // len(releases)])
                    writer.writerow(
                        ["Mediana Releases", sorted(releases)[len(releases) // 2]]
                    )
                    writer.writerow(
                        ["Média dias desde último push", sum(pushes) // len(pushes)]
                    )
                    writer.writerow(
                        [
                            "Mediana dias desde último push",
                            sorted(pushes)[len(pushes) // 2],
                        ]
                    )
                    writer.writerow([])

        return True

    except Exception as e:
        print(f"Erro ao exportar CSV: {e}")
        return False
