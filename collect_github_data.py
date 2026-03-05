import requests
import csv
from datetime import datetime
import time


# Configuração da API do GitHub
GITHUB_API_URL = "https://api.github.com/graphql"
GITHUB_TOKEN = "seu_token_aqui"

# Query GraphQL repos mais poupulares
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
          stargazerCount
          pullRequests(states: MERGED) {
            totalCount
          }
          releases {
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


def fetch_repositories(cursor=None, page_size=10):
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Content-Type": "application/json",
    }

    variables = {"cursor": cursor, "pageSize": page_size}

    payload = {"query": GRAPHQL_QUERY, "variables": variables}

    try:
        response = requests.post(GITHUB_API_URL, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Erro na requisição: {e}")
        return None


def display_repository_data(repos, start_index):
    print("\n" + "=" * 100)
    print(
        f"{'#':<5} {'Repositório':<40} {'Idade':<25} {'PRs Aceitas':<15} {'Releases':<10}"
    )
    print("=" * 100)

    for i, repo in enumerate(repos, start=start_index + 1):
        node = repo["node"]
        name = f"{node['owner']['login']}/{node['name']}"
        age_days = calculate_age_in_days(node["createdAt"])
        age_formatted = format_age(age_days)
        pr_count = node["pullRequests"]["totalCount"]
        release_count = node["releases"]["totalCount"]
        stars = node["stargazerCount"]

        # Para nomes muito longos
        if len(name) > 38:
            name = name[:35] + "..."

        print(
            f"{i:<5} {name:<40} {age_formatted:<25} {pr_count:<15} {release_count:<10}"
        )

    print("=" * 100)


def collect_statistics(all_repos):
    if not all_repos:
        return

    ages = [calculate_age_in_days(repo["node"]["createdAt"]) for repo in all_repos]
    pr_counts = [repo["node"]["pullRequests"]["totalCount"] for repo in all_repos]
    release_counts = [repo["node"]["releases"]["totalCount"] for repo in all_repos]

    print("\n" + "=" * 100)
    print("ESTATÍSTICAS GERAIS")
    print("=" * 100)

    print("\nRQ01 - Idade dos Repositórios:")
    print(f"  Idade Média: {format_age(sum(ages) // len(ages))}")
    print(f"  Idade Mínima: {format_age(min(ages))}")
    print(f"  Idade Máxima: {format_age(max(ages))}")

    print("\nRQ02 - Pull Requests Aceitas:")
    print(f"  Média de PRs: {sum(pr_counts) // len(pr_counts)}")
    print(f"  Mínimo de PRs: {min(pr_counts)}")
    print(f"  Máximo de PRs: {max(pr_counts)}")

    print("\nRQ03 - Releases:")
    print(f"  Média de Releases: {sum(release_counts) // len(release_counts)}")
    print(f"  Mínimo de Releases: {min(release_counts)}")
    print(f"  Máximo de Releases: {max(release_counts)}")

    print("=" * 100)


def main():
    """Função principal"""
    print("=" * 100)
    print("ANÁLISE DE REPOSITÓRIOS POPULARES DO GITHUB")
    print("Coletando dados dos repositórios com mais estrelas")
    print("=" * 100)

    # check se o token foi configurado
    if GITHUB_TOKEN == "seu_token_aqui":
        print("\n   ATENÇÃO: Configure seu token do GitHub na variável GITHUB_TOKEN")
        print("   Acesse: https://github.com/settings/tokens")
        print("   Crie um token com permissão repositorios publicos\n")
        return

    all_repos = []
    cursor = None
    page_size = 10
    total_fetched = 0
    max_repos = 100

    print(
        f"\nBuscando {max_repos} repositórios com paginação de {page_size} itens...\n"
    )

    while total_fetched < max_repos:
        print(f"Buscando página {(total_fetched // page_size) + 1}...")

        data = fetch_repositories(cursor, page_size)

        if not data or "data" not in data:
            print("Erro ao buscar dados ou limite de requisições atingido")
            break

        if "errors" in data:
            print(f"Erro na query GraphQL: {data['errors']}")
            break

        search_data = data["data"]["search"]
        repos = search_data["edges"]

        if not repos:
            print("Nenhum repositório encontrado")
            break

        # página atual
        display_repository_data(repos, total_fetched)

        all_repos.extend(repos)
        total_fetched += len(repos)

        # verifica se há mais páginas
        page_info = search_data["pageInfo"]
        if not page_info["hasNextPage"] or total_fetched >= max_repos:
            break

        cursor = page_info["endCursor"]

        # rate limit da API
        print("\nAguardando 2 segundos antes da próxima requisição...")
        time.sleep(2)

    print(f"\n  Total de repositórios coletados: {len(all_repos)}")

    if all_repos:
        collect_statistics(all_repos)

        # salvar em .csv para uso futuro
        print("\n")
        save = input("Deseja salvar os dados em CSV? (s/n): ")
        if save.lower() == "s":
            filename = f"github_repos_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            with open(filename, "w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(
                    [
                        "Repositório",
                        "Owner",
                        "Nome",
                        "Estrelas",
                        "Data Criação",
                        "Idade (dias)",
                        "PRs Aceitas",
                        "Releases",
                    ]
                )
                for repo in all_repos:
                    node = repo["node"]
                    full_name = f"{node['owner']['login']}/{node['name']}"
                    age_days = calculate_age_in_days(node["createdAt"])
                    writer.writerow(
                        [
                            full_name,
                            node["owner"]["login"],
                            node["name"],
                            node["stargazerCount"],
                            node["createdAt"],
                            age_days,
                            node["pullRequests"]["totalCount"],
                            node["releases"]["totalCount"],
                        ]
                    )
            print(f"  Dados salvos em: {filename}")


if __name__ == "__main__":
    main()
