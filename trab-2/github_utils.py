import requests
import time
import csv
from datetime import datetime


GITHUB_API_URL = "seu_token_aqui"  # Substitua pelo seu token de acesso pessoal do GitHub

# Query preparada para buscar repositórios Java ordenados por estrelas
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


def fetch_repositories(token, cursor=None, page_size=100, retries=3):
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    variables = {"cursor": cursor, "pageSize": page_size}
    payload = {"query": GRAPHQL_QUERY, "variables": variables}

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

