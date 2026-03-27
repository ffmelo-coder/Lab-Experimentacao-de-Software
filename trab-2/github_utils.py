import os
import csv
import json
import shutil
import statistics
import subprocess
import tempfile
import time
import requests
from datetime import datetime


GITHUB_API_URL = "https://api.github.com/graphql"

# Query
GRAPHQL_QUERY = """
query ($cursor: String, $pageSize: Int!) {
  search(query: "language:Java sort:stars-desc", type: REPOSITORY, first: $pageSize, after: $cursor) {
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


def fetch_repositories(token, cursor=None, page_size=10, retries=3, stars_max=None):
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    stars_filter = f" stars:<{stars_max}" if stars_max is not None else ""
    query = GRAPHQL_QUERY.replace(
        '"language:Java sort:stars-desc"',
        f'"language:Java sort:stars-desc{stars_filter}"',
    )

    variables = {"cursor": cursor, "pageSize": page_size}
    payload = {"query": query, "variables": variables}

    for attempt in range(retries):
        try:
            response = requests.post(
                GITHUB_API_URL,
                headers=headers,
                json=payload,
                timeout=(10, 30),
            )
            response.raise_for_status()
            return response.json()

        except requests.exceptions.Timeout as e:
            if attempt < retries - 1:
                wait_time = 2**attempt
                print(
                    f"Timeout na tentativa {attempt + 1}. Aguardando {wait_time}s antes de tentar novamente..."
                )
                time.sleep(wait_time)
            else:
                print(
                    f"Erro: Timeout após {retries} tentativas. Verifique sua conexão com internet."
                )
                return None

        except requests.exceptions.RequestException as e:
            if attempt < retries - 1:
                print(f"Erro na tentativa {attempt + 1}: {e}. Tentando novamente...")
                time.sleep(2)
            else:
                print(f"Erro na requisição após {retries} tentativas: {e}")
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


# Clonagem e métricas locais
def run_git_clone(clone_url, dest_dir, timeout=300):
    try:
        if os.path.exists(dest_dir):
            return True, "exists"
        os.makedirs(os.path.dirname(dest_dir), exist_ok=True)
        # baixa apenas arquivos .java
        steps = [
            [
                "git",
                "-c",
                "core.longpaths=true",
                "clone",
                "--depth",
                "1",
                "--filter=blob:none",
                "--sparse",
                "--no-checkout",
                clone_url,
                dest_dir,
            ],
            ["git", "-C", dest_dir, "sparse-checkout", "set", "--no-cone", "**/*.java"],
            ["git", "-C", dest_dir, "-c", "core.longpaths=true", "checkout"],
        ]
        for cmd in steps:
            proc = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=timeout,
            )
            if proc.returncode != 0:
                return False, proc.stderr
        return True, "ok"
    except Exception as e:
        return False, str(e)


def run_cloc(repo_dir, cloc_cmd="cloc"):
    try:
        proc = subprocess.run(
            [cloc_cmd, "--json", "--include-lang=Java", repo_dir],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
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
    code = 0
    comments = 0
    blanks = 0
    for root, _, files in os.walk(repo_dir):
        for f in files:
            if f.endswith(".java"):
                path = os.path.join(root, f)
                try:
                    with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                        in_block = False
                        for line in fh:
                            s = line.strip()
                            if not s:
                                blanks += 1
                                continue
                            if in_block:
                                comments += 1
                                if "*/" in s:
                                    in_block = False
                                continue
                            if s.startswith("//"):
                                comments += 1
                            elif s.startswith("/*"):
                                comments += 1
                                if "*/" not in s:
                                    in_block = True
                            else:
                                code += 1
                except Exception:
                    continue
    return code, comments, blanks


def run_ck_for_repo(repo_dir, ck_cmd_template, timeout=300):
    out_dir = tempfile.mkdtemp(prefix="ck_out_")
    cmd = ck_cmd_template.format(repo_dir=repo_dir, out_dir=out_dir)
    try:
        proc = subprocess.run(
            cmd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
        )
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
    for root, _, files in os.walk(out_dir):
        for f in files:
            path = os.path.join(root, f)
            if f.lower().endswith(".json"):
                try:
                    with open(path, "r", encoding="utf-8") as fh:
                        data = json.load(fh)
                        values = []
                        if isinstance(data, list):
                            for item in data:
                                if isinstance(item, dict):
                                    values.append(item)
                        elif isinstance(data, dict):
                            for v in data.values():
                                if isinstance(v, list):
                                    values = v
                                    break

                        if not values:
                            continue

                        cbo_list, dit_list, lcom_list = [], [], []
                        for cls in values:
                            if not isinstance(cls, dict):
                                continue

                            def getf(d, keys):
                                for k in keys:
                                    if k in d:
                                        try:
                                            return float(d[k])
                                        except:
                                            try:
                                                return float(d[k].replace(",", "."))
                                            except:
                                                pass
                                return None

                            cbo = getf(cls, ["cbo", "coupling"])
                            dit = getf(cls, ["dit", "depthInInheritanceTree", "depth"])
                            lcom = getf(cls, ["lcom", "lcom4", "lackOfCohesion"])
                            if cbo is not None:
                                cbo_list.append(cbo)
                            if dit is not None:
                                dit_list.append(dit)
                            if lcom is not None:
                                lcom_list.append(lcom)

                        result = {}
                        if cbo_list:
                            result["cbo_mean"] = round(statistics.mean(cbo_list), 4)
                            result["cbo_median"] = round(statistics.median(cbo_list), 4)
                        if dit_list:
                            result["dit_mean"] = round(statistics.mean(dit_list), 4)
                            result["dit_median"] = round(statistics.median(dit_list), 4)
                        if lcom_list:
                            result["lcom_mean"] = round(statistics.mean(lcom_list), 4)
                            result["lcom_median"] = round(statistics.median(lcom_list), 4)
                        return result
                except Exception:
                    continue

            if f.lower().endswith(".csv"):
                try:
                    with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                        reader = csv.DictReader(fh)
                        cbo_list, dit_list, lcom_list = [], [], []
                        for row in reader:
                            lower_map = {k.lower(): v for k, v in row.items()}

                            def get_from_map(m, names):
                                for n in names:
                                    if n in m and m[n] not in (None, ""):
                                        try:
                                            return float(m[n])
                                        except:
                                            try:
                                                return float(m[n].replace(",", "."))
                                            except:
                                                pass
                                return None

                            cbo = get_from_map(lower_map, ["cbo"])
                            dit = get_from_map(lower_map, ["dit"])
                            lcom = get_from_map(lower_map, ["lcom"])
                            if cbo is not None:
                                cbo_list.append(cbo)
                            if dit is not None:
                                dit_list.append(dit)
                            if lcom is not None:
                                lcom_list.append(lcom)

                        result = {}
                        if cbo_list:
                            result["cbo_mean"] = round(statistics.mean(cbo_list), 4)
                            result["cbo_median"] = round(statistics.median(cbo_list), 4)
                        if dit_list:
                            result["dit_mean"] = round(statistics.mean(dit_list), 4)
                            result["dit_median"] = round(statistics.median(dit_list), 4)
                        if lcom_list:
                            result["lcom_mean"] = round(statistics.mean(lcom_list), 4)
                            result["lcom_median"] = round(statistics.median(lcom_list), 4)
                        return result
                except Exception:
                    continue

    return None


# Escrita de CSVs


def write_list_csv(edges, filename):
    header = [
        "Rank",
        "Repositório",
        "Owner",
        "Nome",
        "Estrelas",
        "Linguagem Primária",
        "Data Criação",
        "Idade (dias)",
        "Último Push",
        "Dias desde Último Push",
        "Releases",
        "PRs Aceitas (Merged)",
        "Total Issues",
        "Issues Fechadas",
        "% Issues Fechadas",
    ]
    with open(filename, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        for rank, edge in enumerate(edges, start=1):
            node = edge["node"]
            owner = node["owner"]["login"]
            name = node["name"]
            created_at = node.get("createdAt", "")
            age_days = calculate_age_in_days(created_at) if created_at else ""
            pushed_at = node.get("pushedAt", "")
            days_since = calculate_days_since_push(pushed_at) if pushed_at else ""
            total_issues = node.get("issues", {}).get("totalCount", 0)
            closed_issues = node.get("closedIssues", {}).get("totalCount", 0)
            pct = calculate_closed_issues_ratio(closed_issues, total_issues)
            language = (
                node.get("primaryLanguage", {}).get("name")
                if node.get("primaryLanguage")
                else "Java"
            )
            w.writerow(
                [
                    rank,
                    f"{owner}/{name}",
                    owner,
                    name,
                    node.get("stargazerCount", 0),
                    language,
                    created_at,
                    age_days,
                    pushed_at,
                    days_since,
                    node.get("releases", {}).get("totalCount", 0),
                    node.get("pullRequests", {}).get("totalCount", 0),
                    total_issues,
                    closed_issues,
                    f"{pct:.2f}",
                ]
            )


def write_results_csv(rows, filename):
    header = [
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
        "LOC Java",
        "Comments Java",
        "Blank Java",
        "CBO_Mean",
        "CBO_Median",
        "DIT_Mean",
        "DIT_Median",
        "LCOM_Mean",
        "LCOM_Median",
    ]
    with open(filename, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        for r in rows:
            w.writerow(
                [
                    r.get("full_name"),
                    r.get("owner"),
                    r.get("name"),
                    r.get("stars"),
                    r.get("language"),
                    r.get("createdAt"),
                    r.get("age_days"),
                    r.get("pushedAt"),
                    r.get("days_since_push"),
                    r.get("pr_count"),
                    r.get("release_count"),
                    r.get("total_issues"),
                    r.get("closed_issues"),
                    r.get("pct_issues"),
                    r.get("loc_java"),
                    r.get("comments_java"),
                    r.get("blank_java"),
                    r.get("cbo_mean"),
                    r.get("cbo_median"),
                    r.get("dit_mean"),
                    r.get("dit_median"),
                    r.get("lcom_mean"),
                    r.get("lcom_median"),
                ]
            )
