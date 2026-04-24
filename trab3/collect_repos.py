import time
import argparse
from github_utils import validate_token, fetch_repositories, export_repos_csv

GITHUB_TOKEN = "SEU_TOKEN_AQUI"


def display_repos(repos, start_index):
    print("\n" + "=" * 110)
    print(
        f"{'#':<5} {'Repositório':<45} {'Estrelas':<12} {'Linguagem':<15} {'Merged':<10} {'Closed':<10} {'Total':<8}"
    )
    print("=" * 110)

    for i, repo in enumerate(repos, start=start_index + 1):
        node = repo["node"]
        name = f"{node['owner']['login']}/{node['name']}"
        stars = node["stargazerCount"]
        language = node["primaryLanguage"]["name"] if node["primaryLanguage"] else "N/A"
        merged = node["mergedPRs"]["totalCount"]
        closed = node["closedPRs"]["totalCount"]
        total = merged + closed

        if len(name) > 43:
            name = name[:40] + "..."
        if len(language) > 13:
            language = language[:13]

        print(
            f"{i:<5} {name:<45} {stars:<12} {language:<15} {merged:<10} {closed:<10} {total:<8}"
        )

    print("=" * 110)


def main():
    parser = argparse.ArgumentParser(
        description="Coleta e filtra os repositórios mais populares do GitHub para análise de code review"
    )
    parser.add_argument(
        "--target",
        type=int,
        default=200,
        help="Número de repositórios selecionados desejados (padrão: 200)",
    )
    parser.add_argument(
        "--min-prs",
        type=int,
        default=100,
        help="Mínimo de PRs (Merged+Closed) para seleção (padrão: 100)",
    )
    parser.add_argument(
        "--per-page",
        type=int,
        default=20,
        help="Itens por página da API (max 100, padrão: 20)",
    )
    parser.add_argument(
        "--output",
        default="repos_selecionados.csv",
        help="Arquivo CSV de saída (padrão: repos_selecionados.csv)",
    )
    args = parser.parse_args()

    token = GITHUB_TOKEN
    if not token or token == "seu_token_aqui":
        print("Defina GITHUB_TOKEN no topo do arquivo collect_repos.py")
        return

    if not validate_token(token):
        print("Token inválido ou sem permissão. Verifique.")
        return

    all_scanned = []
    selected = []
    seen_names = set()
    cursor = None
    page_num = 0

    print("=" * 110)
    print("COLETA DE REPOSITÓRIOS POPULARES DO GITHUB - LAB 03")
    print(
        f"Coletando {args.target} repositórios com >= {args.min_prs} PRs (Merged+Closed)"
    )
    print("=" * 110)

    while len(selected) < args.target:
        page_num += 1

        print(f"\nBuscando página {page_num} ({len(selected)}/{args.target} selecionados)...")

        data = fetch_repositories(token, cursor, args.per_page)

        if not data or "data" not in data:
            print("Erro ao buscar dados ou limite de requisições atingido")
            break

        if "errors" in data:
            print("Erro na query GraphQL:", data["errors"])
            break

        search_data = data["data"]["search"]
        edges = search_data["edges"]

        if not edges:
            break

        new_edges = [
            e
            for e in edges
            if f"{e['node']['owner']['login']}/{e['node']['name']}" not in seen_names
        ]
        for e in new_edges:
            seen_names.add(f"{e['node']['owner']['login']}/{e['node']['name']}")

        if new_edges:
            display_repos(new_edges, len(all_scanned))
            all_scanned.extend(new_edges)
            new_selected = [
                r for r in new_edges
                if (r["node"]["mergedPRs"]["totalCount"] + r["node"]["closedPRs"]["totalCount"])
                >= args.min_prs
            ]
            selected.extend(new_selected)

        page_info = search_data.get("pageInfo", {})
        if not page_info.get("hasNextPage"):
            break

        cursor = page_info.get("endCursor")
        time.sleep(1)

    final = selected[:args.target]

    print(f"\n{'=' * 110}")
    print("RESULTADO DA SELEÇÃO")
    print(f"{'=' * 110}")
    print(f"Repositórios escaneados  : {len(all_scanned)}")
    print(f"Repositórios selecionados: {len(final)} (com >= {args.min_prs} PRs Merged+Closed)")
    print(f"{'=' * 110}")

    if final:
        print(f"\nLista final dos repositórios selecionados:")
        display_repos(final, 0)

    print(f"\nGravando lista em '{args.output}'...")
    if export_repos_csv(final, args.output):
        print(f"Concluído. {len(final)} repositórios salvos em '{args.output}'.")
    else:
        print("Erro ao salvar CSV.")


if __name__ == "__main__":
    main()
