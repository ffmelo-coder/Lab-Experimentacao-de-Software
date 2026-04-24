import requests
import aiohttp
import asyncio
import csv
import time
from datetime import datetime


GITHUB_API_URL = "https://api.github.com/graphql"

GRAPHQL_QUERY = """
query ($cursor: String, $pageSize: Int!) {
  search(query: "stars:>1 sort:stars-desc", type: REPOSITORY, first: $pageSize, after: $cursor) {
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
          stargazerCount
          createdAt
          primaryLanguage {
            name
          }
          mergedPRs: pullRequests(states: MERGED) {
            totalCount
          }
          closedPRs: pullRequests(states: CLOSED) {
            totalCount
          }
        }
      }
    }
  }
}
"""


def validate_token(token):
    query = "query { viewer { login } }"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    try:
        response = requests.post(
            GITHUB_API_URL,
            headers=headers,
            json={"query": query},
            timeout=10,
        )
        data = response.json()
        return "errors" not in data and "data" in data
    except Exception:
        return False


def fetch_repositories(token, cursor=None, page_size=20, retries=3):
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
        except requests.exceptions.Timeout:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
            else:
                return None
        except requests.exceptions.RequestException:
            if attempt < retries - 1:
                time.sleep(2)
            else:
                return None

    return None


GRAPHQL_PR_QUERY = """
query ($owner: String!, $name: String!, $cursor: String, $pageSize: Int!) {
  repository(owner: $owner, name: $name) {
    pullRequests(
      states: [MERGED, CLOSED]
      first: $pageSize
      after: $cursor
      orderBy: { field: CREATED_AT, direction: DESC }
    ) {
      pageInfo {
        endCursor
        hasNextPage
      }
      nodes {
        number
        title
        state
        createdAt
        mergedAt
        closedAt
        body
        changedFiles
        additions
        deletions
        author {
          login
        }
        reviews {
          totalCount
        }
        participants {
          totalCount
        }
        comments {
          totalCount
        }
      }
    }
  }
}
"""

PR_CSV_HEADERS = [
    "repo",
    "pr_number",
    "title",
    "state",
    "author",
    "created_at",
    "closed_at",
    "time_to_close_hours",
    "changed_files",
    "additions",
    "deletions",
    "total_changes",
    "body_length",
    "reviews_count",
    "participants_count",
    "comments_count",
]


def fetch_pull_requests(token, owner, name, cursor=None, page_size=50, retries=3):
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    variables = {
        "owner": owner,
        "name": name,
        "cursor": cursor,
        "pageSize": page_size,
    }
    payload = {"query": GRAPHQL_PR_QUERY, "variables": variables}

    for attempt in range(retries):
        try:
            response = requests.post(
                GITHUB_API_URL,
                headers=headers,
                json=payload,
                timeout=(10, 60),
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.Timeout:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
            else:
                return None
        except requests.exceptions.RequestException:
            if attempt < retries - 1:
                time.sleep(2)
            else:
                return None

    return None


async def async_validate_token(token, session):
    query = "query { viewer { login } }"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    try:
        async with session.post(
            GITHUB_API_URL,
            headers=headers,
            json={"query": query},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            data = await resp.json()
            return "errors" not in data and "data" in data
    except Exception:
        return False


async def async_fetch_pull_requests(
    token, owner, name, cursor=None, page_size=50, retries=3, session=None
):
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    variables = {
        "owner": owner,
        "name": name,
        "cursor": cursor,
        "pageSize": page_size,
    }
    payload = {"query": GRAPHQL_PR_QUERY, "variables": variables}

    for attempt in range(retries):
        try:
            async with session.post(
                GITHUB_API_URL,
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(connect=10, total=60),
            ) as resp:
                resp.raise_for_status()
                return await resp.json()
        except asyncio.TimeoutError:
            if attempt < retries - 1:
                await asyncio.sleep(2 ** attempt)
            else:
                return None
        except Exception:
            if attempt < retries - 1:
                await asyncio.sleep(2)
            else:
                return None

    return None


def init_prs_csv(filename):
    try:
        with open(filename, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(PR_CSV_HEADERS)
        return True
    except Exception:
        return False


def append_prs_csv(filename, rows):
    if not rows:
        return True
    try:
        with open(filename, "a", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=PR_CSV_HEADERS)
            for row in rows:
                writer.writerow(row)
        return True
    except Exception:
        return False


def export_repos_csv(repos, filename):
    if not repos:
        return False
    try:
        with open(filename, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "Rank",
                "Repositório",
                "Owner",
                "Nome",
                "Estrelas",
                "Linguagem",
                "PRs Merged",
                "PRs Closed",
                "Total PRs (Merged+Closed)",
                "Data Criação",
            ])
            for i, repo in enumerate(repos, start=1):
                node = repo["node"]
                merged = node["mergedPRs"]["totalCount"]
                closed = node["closedPRs"]["totalCount"]
                language = node["primaryLanguage"]["name"] if node["primaryLanguage"] else "N/A"
                writer.writerow([
                    i,
                    f"{node['owner']['login']}/{node['name']}",
                    node["owner"]["login"],
                    node["name"],
                    node["stargazerCount"],
                    language,
                    merged,
                    closed,
                    merged + closed,
                    node["createdAt"],
                ])
        return True
    except Exception:
        return False
