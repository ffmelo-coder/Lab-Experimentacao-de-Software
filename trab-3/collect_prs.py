import csv
import asyncio
import aiohttp
import argparse
from datetime import datetime
from github_utils import (
    async_validate_token,
    async_fetch_pull_requests,
    init_prs_csv,
    append_prs_csv,
)

GITHUB_TOKEN = "SEU-TOKEN-AQUI"


def read_repos_csv(filename):
    repos = []
    with open(filename, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            repos.append({"owner": row["Owner"], "name": row["Nome"]})
    return repos


def parse_pr(node, repo_full_name):
    state = node["state"]
    created_at = node["createdAt"]
    end_at = node.get("mergedAt") if state == "MERGED" else node.get("closedAt")

    if not end_at:
        return None

    created_dt = datetime.strptime(created_at, "%Y-%m-%dT%H:%M:%SZ")
    end_dt = datetime.strptime(end_at, "%Y-%m-%dT%H:%M:%SZ")
    hours = (end_dt - created_dt).total_seconds() / 3600

    if hours <= 1:
        return None

    reviews_count = node["reviews"]["totalCount"]
    if reviews_count < 1:
        return None

    body = node.get("body") or ""

    return {
        "repo": repo_full_name,
        "pr_number": node["number"],
        "title": node["title"],
        "state": state,
        "author": node["author"]["login"] if node.get("author") else "ghost",
        "created_at": created_at,
        "closed_at": end_at,
        "time_to_close_hours": round(hours, 4),
        "changed_files": node["changedFiles"],
        "additions": node["additions"],
        "deletions": node["deletions"],
        "total_changes": node["additions"] + node["deletions"],
        "body_length": len(body),
        "reviews_count": reviews_count,
        "participants_count": node["participants"]["totalCount"],
        "comments_count": node["comments"]["totalCount"],
    }


async def process_repo(session, semaphore, csv_lock, token, repo, idx, total, args):
    owner = repo["owner"]
    name = repo["name"]
    full_name = f"{owner}/{name}"

    async with semaphore:
        print(f"\n[{idx}/{total}] {full_name}")

        repo_prs = []
        repo_raw = 0
        cursor = None
        page_num = 0

        while True:
            if args.max_prs > 0 and len(repo_prs) >= args.max_prs:
                break

            page_num += 1
            data = None
            for attempt in range(args.page_retries + 1):
                raw = await async_fetch_pull_requests(
                    token, owner, name, cursor, args.per_page, session=session
                )
                if (
                    raw
                    and "data" in raw
                    and raw["data"].get("repository")
                    and "errors" not in raw
                ):
                    data = raw
                    break
                label = f"tentativa {attempt + 1}/{args.page_retries + 1}"
                if "errors" in (raw or {}):
                    reason = f"Erro GraphQL: {raw['errors']}"
                else:
                    reason = "sem dados"
                if attempt < args.page_retries:
                    wait = 5 * (2**attempt)
                    print(
                        f"  [{full_name}] Página {page_num} {reason} ({label}), aguardando {wait}s..."
                    )
                    await asyncio.sleep(wait)
                else:
                    print(
                        f"  [{full_name}] Página {page_num} {reason} — esgotadas {args.page_retries + 1} tentativas, abortando repo"
                    )

            if data is None:
                break

            pr_data = data["data"]["repository"]["pullRequests"]
            nodes = pr_data["nodes"]

            if not nodes:
                break

            repo_raw += len(nodes)
            page_valid = 0
            for node in nodes:
                parsed = parse_pr(node, full_name)
                if parsed:
                    repo_prs.append(parsed)
                    page_valid += 1

            print(
                f"  [{full_name}] Página {page_num}: {len(nodes)} PRs"
                f" | Válidos: {page_valid} | Acumulado: {len(repo_prs)}"
            )

            page_info = pr_data["pageInfo"]
            if not page_info["hasNextPage"]:
                break

            cursor = page_info["endCursor"]
            if args.delay > 0:
                await asyncio.sleep(args.delay)

        if args.max_prs > 0:
            repo_prs = repo_prs[: args.max_prs]

        async with csv_lock:
            append_prs_csv(args.output, repo_prs)

        print(f"  [{full_name}] Concluído: {len(repo_prs)} PRs válidos")
        return repo_prs, repo_raw


async def async_main(args, token, repos):
    semaphore = asyncio.Semaphore(args.concurrency)
    csv_lock = asyncio.Lock()

    connector = aiohttp.TCPConnector(limit=args.concurrency * 2)
    async with aiohttp.ClientSession(connector=connector) as session:
        if not await async_validate_token(token, session):
            print("Token inválido ou sem permissão. Verifique.")
            return 0, 0

        tasks = [
            process_repo(session, semaphore, csv_lock, token, repo, i, len(repos), args)
            for i, repo in enumerate(repos, start=1)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    total_prs = 0
    total_raw = 0
    for r in results:
        if isinstance(r, Exception) or r is None:
            continue
        prs, raw = r
        total_prs += len(prs)
        total_raw += raw

    return total_prs, total_raw


def main():
    parser = argparse.ArgumentParser(
        description="Coleta PRs e métricas dos repositórios selecionados para análise de code review"
    )
    parser.add_argument(
        "--repos",
        default="repos_selecionados.csv",
        help="CSV com repositórios selecionados (padrão: repos_selecionados.csv)",
    )
    parser.add_argument(
        "--output",
        default="prs_coletados.csv",
        help="CSV de saída (padrão: prs_coletados.csv)",
    )
    parser.add_argument(
        "--max-prs",
        type=int,
        default=0,
        help="Máximo de PRs válidos por repositório, 0=ilimitado (padrão: 0)",
    )
    parser.add_argument(
        "--per-page",
        type=int,
        default=50,
        help="PRs por página da API, max 100 (padrão: 50)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=5,
        help="Repositórios processados em paralelo (padrão: 5)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.0,
        help="Delay em segundos entre páginas de um mesmo repositório (padrão: 0.0)",
    )
    parser.add_argument(
        "--page-retries",
        type=int,
        default=3,
        help="Tentativas extras por página em caso de erro (padrão: 3)",
    )
    args = parser.parse_args()

    token = GITHUB_TOKEN
    if not token or token == "seu_token_aqui":
        print("Defina GITHUB_TOKEN no topo do arquivo collect_prs.py")
        return

    try:
        repos = read_repos_csv(args.repos)
    except FileNotFoundError:
        print(
            f"Arquivo '{args.repos}' não encontrado. Execute collect_repos.py primeiro."
        )
        return

    print("=" * 100)
    print("COLETA DE PULL REQUESTS - LAB 03 (async)")
    print(
        f"Repositórios: {len(repos)}"
        f" | Concorrência: {args.concurrency}"
        f" | Filtros: >= 1 review, tempo de análise > 1h"
    )
    print("=" * 100)

    if not init_prs_csv(args.output):
        print(f"Erro ao criar arquivo '{args.output}'")
        return

    total_prs, total_raw = asyncio.run(async_main(args, token, repos))

    print(f"\n{'=' * 100}")
    print("COLETA CONCLUÍDA")
    print(f"PRs brutos processados  : {total_raw}")
    print(f"PRs válidos coletados   : {total_prs}")
    print(f"PRs filtrados           : {total_raw - total_prs}")
    print(f"Arquivo gerado          : '{args.output}'")
    print(f"{'=' * 100}")


if __name__ == "__main__":
    main()
