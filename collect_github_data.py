import time
from datetime import datetime
from github_utils import (
    calculate_age_in_days,
    format_age,
    calculate_days_since_push,
    calculate_closed_issues_ratio,
    fetch_repositories,
    export_to_csv,
)

GITHUB_TOKEN = "seu_token_aqui"


def display_repository_data(repos, start_index):
    print("\n" + "=" * 130)
    print(
        f"{'#':<5} {'Repositório':<35} {'Linguagem':<12} {'Idade':<20} {'PRs':<8} {'Releases':<10} {'Issues %':<10}"
    )
    print("=" * 130)

    for i, repo in enumerate(repos, start=start_index + 1):
        node = repo["node"]
        name = f"{node['owner']['login']}/{node['name']}"
        age_days = calculate_age_in_days(node["createdAt"])
        age_formatted = format_age(age_days)
        pr_count = node["pullRequests"]["totalCount"]
        release_count = node["releases"]["totalCount"]
        language = node["primaryLanguage"]["name"] if node["primaryLanguage"] else "N/A"
        total_issues = node["issues"]["totalCount"]
        closed_issues = node["closedIssues"]["totalCount"]
        issues_ratio = calculate_closed_issues_ratio(closed_issues, total_issues)

        if len(name) > 33:
            name = name[:30] + "..."
        if len(language) > 10:
            language = language[:10]

        print(
            f"{i:<5} {name:<35} {language:<12} {age_formatted:<20} {pr_count:<8} {release_count:<10} {issues_ratio:<9.1f}%"
        )

    print("=" * 130)


def collect_statistics(all_repos):
    if not all_repos:
        return

    ages = [calculate_age_in_days(repo["node"]["createdAt"]) for repo in all_repos]
    pr_counts = [repo["node"]["pullRequests"]["totalCount"] for repo in all_repos]
    release_counts = [repo["node"]["releases"]["totalCount"] for repo in all_repos]
    days_since_push = [
        calculate_days_since_push(repo["node"]["pushedAt"]) for repo in all_repos
    ]

    issues_ratios = []
    for repo in all_repos:
        node = repo["node"]
        total = node["issues"]["totalCount"]
        closed = node["closedIssues"]["totalCount"]
        issues_ratios.append(calculate_closed_issues_ratio(closed, total))

    print("\n" + "=" * 100)
    print("ESTATÍSTICAS GERAIS - ANÁLISE DOS 1000 REPOSITÓRIOS MAIS POPULARES")
    print("=" * 100)

    print("\nRQ01 - Sistemas populares são maduros/antigos?")
    print(f"  Idade Média: {format_age(sum(ages) // len(ages))}")
    print(f"  Idade Mediana: {format_age(sorted(ages)[len(ages)//2])}")
    print(f"  Idade Mínima: {format_age(min(ages))}")
    print(f"  Idade Máxima: {format_age(max(ages))}")

    print("\nRQ02 - Sistemas populares recebem muita contribuição externa?")
    print(f"  Média de PRs Aceitas: {sum(pr_counts) // len(pr_counts)}")
    print(f"  Mediana de PRs: {sorted(pr_counts)[len(pr_counts)//2]}")
    print(f"  Mínimo de PRs: {min(pr_counts)}")
    print(f"  Máximo de PRs: {max(pr_counts)}")

    print("\nRQ03 - Sistemas populares lançam releases com frequência?")
    print(f"  Média de Releases: {sum(release_counts) // len(release_counts)}")
    print(f"  Mediana de Releases: {sorted(release_counts)[len(release_counts)//2]}")
    print(f"  Mínimo de Releases: {min(release_counts)}")
    print(f"  Máximo de Releases: {max(release_counts)}")

    print("\nRQ04 - Sistemas populares são atualizados com frequência?")
    print(
        f"  Média de dias desde último push: {sum(days_since_push) // len(days_since_push)}"
    )
    print(f"  Mediana: {sorted(days_since_push)[len(days_since_push)//2]} dias")
    print(f"  Mínimo: {min(days_since_push)} dias")
    print(f"  Máximo: {max(days_since_push)} dias")

    print("\nRQ05 - Sistemas populares são escritos nas linguagens mais populares?")
    language_count = {}
    for repo in all_repos:
        lang = repo["node"]["primaryLanguage"]
        lang_name = lang["name"] if lang else "N/A"
        language_count[lang_name] = language_count.get(lang_name, 0) + 1

    sorted_languages = sorted(language_count.items(), key=lambda x: x[1], reverse=True)
    print(f"  Top 10 Linguagens:")
    for lang, count in sorted_languages[:10]:
        percentage = (count / len(all_repos)) * 100
        print(f"    {lang}: {count} repositórios ({percentage:.1f}%)")

    print("\nRQ06 - Sistemas populares possuem alto percentual de issues fechadas?")
    avg_ratio = sum(issues_ratios) / len(issues_ratios)
    print(f"  Média de Issues Fechadas: {avg_ratio:.2f}%")
    print(f"  Mediana: {sorted(issues_ratios)[len(issues_ratios)//2]:.2f}%")
    print(f"  Mínimo: {min(issues_ratios):.2f}%")
    print(f"  Máximo: {max(issues_ratios):.2f}%")

    print("\n" + "=" * 100)
    print("RQ07 - Análise por Linguagem (Top 5)")
    print("=" * 100)

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
                calculate_days_since_push(r["node"]["pushedAt"]) for r in repos_lang
            ]

            print(f"\n{lang} ({count} repositórios):")
            print(
                f"  Média PRs: {sum(prs) // len(prs)} | Mediana: {sorted(prs)[len(prs)//2]}"
            )
            print(
                f"  Média Releases: {sum(releases) // len(releases)} | Mediana: {sorted(releases)[len(releases)//2]}"
            )
            print(
                f"  Média dias desde último push: {sum(pushes) // len(pushes)} | Mediana: {sorted(pushes)[len(pushes)//2]}"
            )

    print("=" * 100)


def main():
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
    max_repos = 1000

    print(
        f"\nBuscando {max_repos} repositórios com paginação de {page_size} itens...\n"
    )

    while total_fetched < max_repos:
        print(f"Buscando página {(total_fetched // page_size) + 1}...")

        data = fetch_repositories(GITHUB_TOKEN, cursor, page_size)

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
        time.sleep(1)

    print(f"\n  Total de repositórios coletados: {len(all_repos)}")

    if all_repos:
        collect_statistics(all_repos)

        # salvar em .csv para uso futuro
        print("\n")
        save = input("Deseja salvar os dados em CSV? (s/n): ")
        if save.lower() == "s":
            filename = f"github_repos_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            if export_to_csv(all_repos, filename):
                print(f"  Dados salvos em: {filename}")
            else:
                print("  Erro ao salvar dados no CSV")


if __name__ == "__main__":
    main()
