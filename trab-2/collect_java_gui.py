import os
import sys
import stat
import shutil
import threading
import time
import csv
import concurrent.futures

import tkinter as tk
from tkinter import ttk, messagebox, filedialog

script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)

try:
    import matplotlib

    matplotlib.use("TkAgg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    import numpy as np

    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False

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

_ck_jar = os.path.join(script_dir, "ck", "ck-0.7.1-SNAPSHOT-jar-with-dependencies.jar")
CK_CMD = f'java -jar "{_ck_jar}" {{repo_dir}} true 0 false {{out_dir}}'


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
        ["cmd", "/c", "rd", "/s", "/q", os.path.abspath(path)],
        capture_output=True,
    )
    if result.returncode != 0 or os.path.exists(path):
        time.sleep(2)
        shutil.rmtree(path, onexc=_remove_readonly)


class JavaRepoAnalyzerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Análise de Repositórios Java - GitHub")
        self.root.geometry("1280x780")
        self.root.resizable(True, True)

        self.token_var = tk.StringVar()
        self.token_var.trace("w", self._on_token_change)
        self.mode_var = tk.StringVar(value="completo")
        self.workers_var = tk.StringVar(value="4")
        self.ck_timeout_var = tk.StringVar(value="120")
        self.repos_dir_var = tk.StringVar(value=os.path.join(script_dir, "repos"))
        self.max_repos_var = tk.StringVar(value="1000")
        self.output_var = tk.StringVar(
            value=os.path.join(script_dir, "java_repos_metrics.csv")
        )

        self.all_rows = []
        self.all_edges = []
        self.filtered_rows = None
        self.current_page = 0
        self.items_per_page = 20
        self.page_input = tk.StringVar(value="0")

        self.is_running = False
        self.stop_flag = False
        self.filter_visible = False
        self._executor = None

        self._setup_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _setup_ui(self):

        top = ttk.Frame(self.root, padding="8")
        top.pack(fill=tk.X)

        ttk.Label(top, text="GitHub Token:", font=("Arial", 10, "bold")).pack(
            side=tk.LEFT, padx=(0, 4)
        )
        ttk.Entry(top, textvariable=self.token_var, width=46, show="*").pack(
            side=tk.LEFT, padx=(0, 8)
        )

        self.btn_start = ttk.Button(
            top, text="▶ Iniciar Coleta", command=self._start, state=tk.DISABLED
        )
        self.btn_start.pack(side=tk.LEFT, padx=4)

        self.btn_stop = ttk.Button(
            top, text="⏹ Parar", command=self._stop, state=tk.DISABLED
        )
        self.btn_stop.pack(side=tk.LEFT, padx=4)

        opt = ttk.Frame(self.root, padding="4 2")
        opt.pack(fill=tk.X)

        ttk.Label(opt, text="Máx. repos:").pack(side=tk.LEFT, padx=(4, 2))
        ttk.Entry(opt, textvariable=self.max_repos_var, width=7).pack(side=tk.LEFT)

        ttk.Label(opt, text="Modo:").pack(side=tk.LEFT, padx=(12, 2))
        ttk.Combobox(
            opt,
            textvariable=self.mode_var,
            state="readonly",
            width=22,
            values=["completo", "sem_clone (sem LOC/CK)", "apenas_listar"],
        ).pack(side=tk.LEFT)

        ttk.Label(opt, text="Workers:").pack(side=tk.LEFT, padx=(14, 2))
        ttk.Spinbox(opt, from_=1, to=16, textvariable=self.workers_var, width=4).pack(
            side=tk.LEFT
        )

        ttk.Label(opt, text="CK timeout (s):").pack(side=tk.LEFT, padx=(10, 2))
        ttk.Spinbox(
            opt,
            from_=30,
            to=600,
            increment=30,
            textvariable=self.ck_timeout_var,
            width=5,
        ).pack(side=tk.LEFT)

        ttk.Label(opt, text="Dir repos:").pack(side=tk.LEFT, padx=(14, 2))
        ttk.Entry(opt, textvariable=self.repos_dir_var, width=28).pack(side=tk.LEFT)
        ttk.Button(
            opt,
            text="…",
            width=2,
            command=lambda: self.repos_dir_var.set(
                filedialog.askdirectory() or self.repos_dir_var.get()
            ),
        ).pack(side=tk.LEFT)

        ttk.Label(opt, text="  CSV saída:").pack(side=tk.LEFT, padx=(10, 2))
        ttk.Entry(opt, textvariable=self.output_var, width=28).pack(side=tk.LEFT)
        ttk.Button(
            opt,
            text="…",
            width=2,
            command=lambda: self.output_var.set(
                filedialog.asksaveasfilename(
                    defaultextension=".csv",
                    filetypes=[("CSV", "*.csv")],
                )
                or self.output_var.get()
            ),
        ).pack(side=tk.LEFT)

        self._prog_frame = ttk.Frame(self.root, padding="8 4")
        self._prog_frame.pack(fill=tk.X)

        ttk.Label(self._prog_frame, text="Progresso:").pack(side=tk.LEFT, padx=(0, 4))
        self.prog_bar = ttk.Progressbar(
            self._prog_frame, length=480, mode="determinate"
        )
        self.prog_bar.pack(side=tk.LEFT)

        self.prog_label = ttk.Label(
            self._prog_frame, text="0%", font=("Arial", 9, "bold")
        )
        self.prog_label.pack(side=tk.LEFT, padx=6)

        self.btn_import = ttk.Button(
            self._prog_frame,
            text="📂 Importar CSV",
            command=self._import_csv,
        )
        self.btn_import.pack(side=tk.LEFT, padx=6)

        self.btn_csv = ttk.Button(
            self._prog_frame,
            text="💾 Exportar CSV",
            command=self._download_csv,
            state=tk.DISABLED,
        )
        self.btn_csv.pack(side=tk.LEFT, padx=4)

        self.btn_graphs = ttk.Button(
            self._prog_frame,
            text="📊 Ver Gráficos",
            command=self._open_graphs,
            state=tk.DISABLED,
        )
        self.btn_graphs.pack(side=tk.LEFT, padx=4)

        self.btn_filter = ttk.Button(
            self._prog_frame,
            text="🔍 Filtros",
            command=self._toggle_filters,
            state=tk.DISABLED,
        )
        self.btn_filter.pack(side=tk.LEFT, padx=4)

        self.filter_frame = ttk.LabelFrame(
            self.root, text="Filtros Avançados", padding="8"
        )

        fr1 = ttk.Frame(self.filter_frame)
        fr1.pack(fill=tk.X, pady=2)

        ttk.Label(fr1, text="Nome contém:").pack(side=tk.LEFT)
        self.f_name = tk.StringVar()
        ttk.Entry(fr1, textvariable=self.f_name, width=16).pack(
            side=tk.LEFT, padx=(2, 12)
        )

        ttk.Label(fr1, text="Estrelas ≥:").pack(side=tk.LEFT)
        self.f_stars_min = tk.StringVar()
        ttk.Entry(fr1, textvariable=self.f_stars_min, width=8).pack(
            side=tk.LEFT, padx=(2, 12)
        )

        ttk.Label(fr1, text="Idade dias min/max:").pack(side=tk.LEFT)
        self.f_age_min = tk.StringVar()
        self.f_age_max = tk.StringVar()
        ttk.Entry(fr1, textvariable=self.f_age_min, width=7).pack(side=tk.LEFT, padx=2)
        ttk.Label(fr1, text="–").pack(side=tk.LEFT)
        ttk.Entry(fr1, textvariable=self.f_age_max, width=7).pack(
            side=tk.LEFT, padx=(2, 12)
        )

        ttk.Label(fr1, text="PRs min/max:").pack(side=tk.LEFT)
        self.f_prs_min = tk.StringVar()
        self.f_prs_max = tk.StringVar()
        ttk.Entry(fr1, textvariable=self.f_prs_min, width=7).pack(side=tk.LEFT, padx=2)
        ttk.Label(fr1, text="–").pack(side=tk.LEFT)
        ttk.Entry(fr1, textvariable=self.f_prs_max, width=7).pack(side=tk.LEFT)

        fr2 = ttk.Frame(self.filter_frame)
        fr2.pack(fill=tk.X, pady=2)

        ttk.Label(fr2, text="Issues % fechadas:").pack(side=tk.LEFT)
        self.f_iss_min = tk.StringVar()
        self.f_iss_max = tk.StringVar()
        ttk.Entry(fr2, textvariable=self.f_iss_min, width=7).pack(side=tk.LEFT, padx=2)
        ttk.Label(fr2, text="–").pack(side=tk.LEFT)
        ttk.Entry(fr2, textvariable=self.f_iss_max, width=7).pack(
            side=tk.LEFT, padx=(2, 12)
        )

        ttk.Label(fr2, text="LOC Java ≥:").pack(side=tk.LEFT)
        self.f_loc_min = tk.StringVar()
        ttk.Entry(fr2, textvariable=self.f_loc_min, width=9).pack(
            side=tk.LEFT, padx=(2, 12)
        )

        ttk.Label(fr2, text="Releases min/max:").pack(side=tk.LEFT)
        self.f_rel_min = tk.StringVar()
        self.f_rel_max = tk.StringVar()
        ttk.Entry(fr2, textvariable=self.f_rel_min, width=7).pack(side=tk.LEFT, padx=2)
        ttk.Label(fr2, text="–").pack(side=tk.LEFT)
        ttk.Entry(fr2, textvariable=self.f_rel_max, width=7).pack(
            side=tk.LEFT, padx=(2, 16)
        )

        ttk.Button(fr2, text="✔ Aplicar", command=self._apply_filters).pack(
            side=tk.LEFT, padx=4
        )
        ttk.Button(fr2, text="✖ Limpar", command=self._clear_filters).pack(side=tk.LEFT)

        self.filter_status = ttk.Label(
            self.filter_frame, text="", font=("Arial", 9, "italic"), foreground="gray"
        )
        self.filter_status.pack(anchor=tk.W)

        tbl = ttk.Frame(self.root, padding="8 4")
        tbl.pack(fill=tk.BOTH, expand=True)

        vsb = ttk.Scrollbar(tbl)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        hsb = ttk.Scrollbar(tbl, orient=tk.HORIZONTAL)
        hsb.pack(side=tk.BOTTOM, fill=tk.X)

        cols = (
            "#",
            "Repositório",
            "Estrelas",
            "Idade (dias)",
            "PRs",
            "Releases",
            "Issues %",
            "Dias Push",
            "LOC Java",
            "CBO Méd.",
            "DIT Méd.",
            "LCOM Méd.",
        )
        self.tree = ttk.Treeview(
            tbl,
            columns=cols,
            show="headings",
            yscrollcommand=vsb.set,
            xscrollcommand=hsb.set,
            height=18,
        )
        vsb.config(command=self.tree.yview)
        hsb.config(command=self.tree.xview)

        widths = [40, 280, 80, 100, 70, 80, 85, 90, 90, 90, 90, 90]
        for col, w in zip(cols, widths):
            self.tree.heading(col, text=col, command=lambda c=col: self._sort_by(c))
            self.tree.column(
                col, width=w, anchor=tk.CENTER if col != "Repositório" else tk.W
            )
        self.tree.pack(fill=tk.BOTH, expand=True)

        nav = ttk.Frame(self.root, padding="8 4")
        nav.pack(fill=tk.X)

        self.btn_prev = ttk.Button(
            nav, text="◀ Anterior", command=self._prev_page, state=tk.DISABLED
        )
        self.btn_prev.pack(side=tk.LEFT, padx=4)

        ttk.Label(nav, text="Página").pack(side=tk.LEFT, padx=(16, 4))
        self.page_entry = ttk.Entry(
            nav, textvariable=self.page_input, width=5, justify=tk.CENTER
        )
        self.page_entry.pack(side=tk.LEFT)
        self.page_entry.bind("<Return>", self._goto_page)
        self.page_total_label = ttk.Label(nav, text="de 0", font=("Arial", 9, "bold"))
        self.page_total_label.pack(side=tk.LEFT, padx=(4, 16))

        self.btn_next = ttk.Button(
            nav, text="Próxima ▶", command=self._next_page, state=tk.DISABLED
        )
        self.btn_next.pack(side=tk.LEFT)

        self.status_label = ttk.Label(
            nav, text="Aguardando início...", font=("Arial", 9), foreground="blue"
        )
        self.status_label.pack(side=tk.RIGHT, padx=10)

    @staticmethod
    def _safe_int(s, default):
        try:
            return int(s.strip())
        except Exception:
            return default

    @staticmethod
    def _safe_float(s, default):
        try:
            return float(s.strip())
        except Exception:
            return default

    def _on_token_change(self, *_):
        state = tk.NORMAL if self.token_var.get().strip() else tk.DISABLED
        self.btn_start.config(state=state)

    def _active_rows(self):
        return self.filtered_rows if self.filtered_rows is not None else self.all_rows

    def _update_status(self, msg, color="blue"):
        self.root.after(0, lambda: self.status_label.config(text=msg, foreground=color))

    def _update_progress(self, pct):
        def _do():
            self.prog_bar["value"] = pct
            self.prog_label.config(text=f"{int(pct)}%")

        self.root.after(0, _do)

    def _start(self):
        if self.is_running:
            return
        token = self.token_var.get().strip()
        self._update_status("Validando token…", "orange")
        self.root.update()
        if not validate_token(token):
            messagebox.showerror("Erro", "Token inválido! Verifique e tente novamente.")
            self._update_status("Token inválido", "red")
            return

        self.is_running = True
        self.stop_flag = False
        self.all_rows = []
        self.all_edges = []
        self.filtered_rows = None
        self.current_page = 0
        self.btn_start.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        self.btn_csv.config(state=tk.DISABLED)
        self.btn_graphs.config(state=tk.DISABLED)
        self.btn_filter.config(state=tk.DISABLED)
        self.prog_bar["value"] = 0

        threading.Thread(
            target=self._collect_thread, args=(token,), daemon=True
        ).start()

    def _stop(self):
        self.stop_flag = True
        self._update_status("Parando após operação atual…", "orange")

    def _collect_thread(self, token):
        try:
            max_repos = self._safe_int(self.max_repos_var.get(), 1000)
            mode = self.mode_var.get()
            skip_clone = mode.startswith("sem_clone")
            list_only = mode.startswith("apenas_listar")
            repos_dir = self.repos_dir_var.get()

            if not skip_clone and not list_only:
                os.makedirs(repos_dir, exist_ok=True)

            seen = set()
            cursor = None
            stars_max = None
            page_num = 0

            while len(self.all_edges) < max_repos and not self.stop_flag:
                page_num += 1
                self._update_status(
                    f"Buscando página {page_num} ({len(self.all_edges)}/{max_repos})…"
                )
                data = fetch_repositories(token, cursor, 10, stars_max=stars_max)
                if not data or "data" not in data:
                    self._update_status("Erro ao buscar dados.", "red")
                    break
                if "errors" in data:
                    self._update_status(f"Erro GraphQL: {data['errors']}", "red")
                    break

                search = data["data"]["search"]
                edges = search.get("edges", [])
                if not edges:
                    break

                new_edges = [
                    e
                    for e in edges
                    if f"{e['node']['owner']['login']}/{e['node']['name']}" not in seen
                ]
                for e in new_edges:
                    seen.add(f"{e['node']['owner']['login']}/{e['node']['name']}")

                for e in new_edges:
                    rank = len(self.all_edges) + 1
                    self.all_edges.append(e)
                    self.all_rows.append(self._edge_to_row(e, rank))

                self._update_progress((len(self.all_edges) / max_repos) * 50)
                self.root.after(0, self._refresh_table)

                page_info = search.get("pageInfo", {})
                if not page_info.get("hasNextPage"):
                    if self.all_edges:
                        min_stars = min(
                            e["node"].get("stargazerCount", 0) for e in self.all_edges
                        )
                        stars_max = min_stars
                        cursor = None
                    else:
                        break
                else:
                    cursor = page_info.get("endCursor")

                time.sleep(0.5)

            self.all_edges = self.all_edges[:max_repos]
            self.all_rows = self.all_rows[:max_repos]

            if list_only:
                self._update_progress(100)
                self.root.after(0, self._refresh_table)
                self._finish_collection()
                return

            total = len(self.all_edges)
            workers = max(1, self._safe_int(self.workers_var.get(), 4))
            ck_timeout = max(30, self._safe_int(self.ck_timeout_var.get(), 120))
            done_count = 0
            done_lock = threading.Lock()

            def _measure(idx, edge, row):
                if self.stop_flag:
                    return
                try:
                    node = edge["node"]
                    owner = node["owner"]["login"]
                    name = node["name"]
                    clone_url = f"https://github.com/{owner}/{name}.git"
                    repo_dir = os.path.join(repos_dir, f"{owner}__{name}")
                    ok, msg = run_git_clone(clone_url, repo_dir)
                    if ok:
                        try:
                            cloc = run_cloc(repo_dir)
                            if cloc:
                                (
                                    row["loc_java"],
                                    row["comments_java"],
                                    row["blank_java"],
                                ) = cloc
                            else:
                                (
                                    row["loc_java"],
                                    row["comments_java"],
                                    row["blank_java"],
                                ) = count_java_loc(repo_dir)
                        except Exception:
                            pass
                        try:
                            ck = run_ck_for_repo(repo_dir, CK_CMD, timeout=ck_timeout)
                            if ck:
                                row.update(ck)
                        except Exception:
                            pass
                        try:
                            remove_dir(repo_dir)
                        except Exception:
                            pass
                    else:
                        self._update_status(
                            f"[{idx}/{total}] Falha clone {owner}/{name}: {msg[:50]}",
                            "orange",
                        )
                except Exception as exc:
                    self._update_status(f"[{idx}/{total}] Erro: {exc}", "orange")

            if skip_clone:

                self._update_progress(100)
            else:
                self._executor = concurrent.futures.ThreadPoolExecutor(
                    max_workers=workers
                )
                pool = self._executor
                futures = {
                    pool.submit(_measure, i, edge, row): i
                    for i, (edge, row) in enumerate(
                        zip(self.all_edges, self.all_rows), 1
                    )
                }

                try:
                    pool.shutdown(wait=False, cancel_futures=False)
                except TypeError:
                    pool.shutdown(wait=False)

                for fut in concurrent.futures.as_completed(futures):
                    if self.stop_flag:
                        for f in futures:
                            f.cancel()
                        break

                    try:
                        fut.result()
                    except Exception:
                        pass
                    with done_lock:
                        done_count += 1
                        pct = 50 + (done_count / total) * 50
                    idx = futures[fut]
                    self._update_status(f"[{done_count}/{total}] medido repo #{idx}…")
                    self._update_progress(pct)
                    self.root.after(0, self._refresh_table)

            self._finish_collection()

        except Exception as exc:
            self._update_status(f"Erro inesperado: {exc}", "red")
            self.root.after(0, self._enable_buttons)

    def _edge_to_row(self, edge, rank):
        node = edge["node"]
        owner = node["owner"]["login"]
        name = node["name"]
        created_at = node.get("createdAt", "")
        pushed_at = node.get("pushedAt", "")
        total_issues = node.get("issues", {}).get("totalCount", 0)
        closed_issues = node.get("closedIssues", {}).get("totalCount", 0)
        return {
            "rank": rank,
            "full_name": f"{owner}/{name}",
            "owner": owner,
            "name": name,
            "stars": node.get("stargazerCount", 0),
            "language": (
                node["primaryLanguage"]["name"]
                if node.get("primaryLanguage")
                else "Java"
            ),
            "createdAt": created_at,
            "age_days": calculate_age_in_days(created_at) if created_at else None,
            "pushedAt": pushed_at,
            "days_since_push": (
                calculate_days_since_push(pushed_at) if pushed_at else None
            ),
            "pr_count": node.get("pullRequests", {}).get("totalCount", 0),
            "release_count": node.get("releases", {}).get("totalCount", 0),
            "total_issues": total_issues,
            "closed_issues": closed_issues,
            "pct_issues": round(
                calculate_closed_issues_ratio(closed_issues, total_issues), 2
            ),
            "loc_java": None,
            "comments_java": None,
            "blank_java": None,
            "cbo_mean": None,
            "cbo_median": None,
            "dit_mean": None,
            "dit_median": None,
            "lcom_mean": None,
            "lcom_median": None,
        }

    def _finish_collection(self):
        self._executor = None
        self._update_progress(100)
        self._update_status(
            f"Concluído — {len(self.all_rows)} repositórios coletados.", "green"
        )
        self.root.after(0, self._enable_buttons)
        self.root.after(0, self._refresh_table)
        self.is_running = False

    def _enable_buttons(self):
        self.btn_start.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.DISABLED)
        self.btn_csv.config(state=tk.NORMAL if self.all_rows else tk.DISABLED)
        self.btn_graphs.config(
            state=tk.NORMAL if self.all_rows and MATPLOTLIB_AVAILABLE else tk.DISABLED
        )
        self.btn_filter.config(state=tk.NORMAL if self.all_rows else tk.DISABLED)
        self.is_running = False

    def _refresh_table(self):
        rows = self._active_rows()
        total_pages = max(
            1, (len(rows) + self.items_per_page - 1) // self.items_per_page
        )
        self.current_page = min(self.current_page, total_pages - 1)

        start = self.current_page * self.items_per_page
        end = start + self.items_per_page
        page_rows = rows[start:end]

        self.tree.delete(*self.tree.get_children())
        for r in page_rows:
            loc = r.get("loc_java")
            cbo = r.get("cbo_mean")
            dit = r.get("dit_mean")
            lcom = r.get("lcom_mean")
            self.tree.insert(
                "",
                tk.END,
                values=(
                    r.get("rank", ""),
                    r.get("full_name", ""),
                    r.get("stars", 0),
                    r.get("age_days", ""),
                    r.get("pr_count", 0),
                    r.get("release_count", 0),
                    f"{r.get('pct_issues', 0):.2f}",
                    r.get("days_since_push", ""),
                    loc if loc is not None else "—",
                    f"{cbo:.2f}" if cbo is not None else "—",
                    f"{dit:.2f}" if dit is not None else "—",
                    f"{lcom:.2f}" if lcom is not None else "—",
                ),
            )

        self.page_input.set(str(self.current_page))
        self.page_total_label.config(text=f"de {total_pages - 1}")
        self.btn_prev.config(state=tk.NORMAL if self.current_page > 0 else tk.DISABLED)
        self.btn_next.config(
            state=tk.NORMAL if self.current_page < total_pages - 1 else tk.DISABLED
        )

    def _prev_page(self):
        if self.current_page > 0:
            self.current_page -= 1
            self._refresh_table()

    def _next_page(self):
        rows = self._active_rows()
        total_pages = max(
            1, (len(rows) + self.items_per_page - 1) // self.items_per_page
        )
        if self.current_page < total_pages - 1:
            self.current_page += 1
            self._refresh_table()

    def _goto_page(self, _event=None):
        try:
            p = int(self.page_input.get())
            rows = self._active_rows()
            total_pages = max(
                1, (len(rows) + self.items_per_page - 1) // self.items_per_page
            )
            self.current_page = max(0, min(p, total_pages - 1))
            self._refresh_table()
        except ValueError:
            pass

    _sort_col = None
    _sort_asc = True

    def _sort_by(self, col):
        key_map = {
            "#": "rank",
            "Repositório": "full_name",
            "Estrelas": "stars",
            "Idade (dias)": "age_days",
            "PRs": "pr_count",
            "Releases": "release_count",
            "Issues %": "pct_issues",
            "Dias Push": "days_since_push",
            "LOC Java": "loc_java",
            "CBO Méd.": "cbo_mean",
            "DIT Méd.": "dit_mean",
            "LCOM Méd.": "lcom_mean",
        }
        k = key_map.get(col, col)
        if self._sort_col == col:
            self._sort_asc = not self._sort_asc
        else:
            self._sort_col = col
            self._sort_asc = True

        def _key(r):
            v = r.get(k)
            if v is None:
                return (1, 0)
            if isinstance(v, (int, float)):
                return (0, v)
            try:
                return (0, float(v))
            except Exception:
                return (0, str(v))

        rows = self._active_rows()
        rows.sort(key=_key, reverse=not self._sort_asc)
        if self.filtered_rows is not None:
            self.filtered_rows = rows
        else:
            self.all_rows = rows
        self.current_page = 0
        self._refresh_table()

    def _toggle_filters(self):
        if self.filter_visible:
            self.filter_frame.pack_forget()
            self.filter_visible = False
            self.btn_filter.config(text="🔍 Filtros")
        else:
            self.filter_frame.pack(
                fill=tk.X, padx=8, pady=(0, 4), after=self._prog_frame
            )
            self.filter_visible = True
            self.btn_filter.config(text="🔍 Fechar Filtros")

    def _apply_filters(self):
        if not self.all_rows:
            return
        name_f = self.f_name.get().strip().lower()
        stars_min = self._safe_int(self.f_stars_min.get(), 0)
        age_min = self._safe_int(self.f_age_min.get(), 0)
        age_max = self._safe_int(self.f_age_max.get(), 10**9)
        prs_min = self._safe_int(self.f_prs_min.get(), 0)
        prs_max = self._safe_int(self.f_prs_max.get(), 10**9)
        iss_min = self._safe_float(self.f_iss_min.get(), 0.0)
        iss_max = self._safe_float(self.f_iss_max.get(), 100.0)
        loc_min = self._safe_int(self.f_loc_min.get(), 0)
        rel_min = self._safe_int(self.f_rel_min.get(), 0)
        rel_max = self._safe_int(self.f_rel_max.get(), 10**9)

        result = []
        for r in self.all_rows:
            if name_f and name_f not in r.get("full_name", "").lower():
                continue
            if r.get("stars", 0) < stars_min:
                continue
            age = r.get("age_days") or 0
            if not (age_min <= age <= age_max):
                continue
            prs = r.get("pr_count", 0)
            if not (prs_min <= prs <= prs_max):
                continue
            iss = r.get("pct_issues", 0)
            if not (iss_min <= iss <= iss_max):
                continue
            loc = r.get("loc_java") or 0
            if loc < loc_min:
                continue
            rel = r.get("release_count", 0)
            if not (rel_min <= rel <= rel_max):
                continue
            result.append(r)

        self.filtered_rows = result
        self.current_page = 0
        self._refresh_table()
        total = len(self.all_rows)
        count = len(result)
        self.filter_status.config(
            text=f"Filtros ativos: {count} de {total} repositórios",
            foreground="green" if count == total else "orange",
        )

    def _clear_filters(self):
        for v in (
            self.f_name,
            self.f_stars_min,
            self.f_age_min,
            self.f_age_max,
            self.f_prs_min,
            self.f_prs_max,
            self.f_iss_min,
            self.f_iss_max,
            self.f_loc_min,
            self.f_rel_min,
            self.f_rel_max,
        ):
            v.set("")
        self.filtered_rows = None
        self.current_page = 0
        self.filter_status.config(text="")
        self._refresh_table()

    def _import_csv(self):
        path = filedialog.askopenfilename(
            title="Importar CSV de métricas",
            filetypes=[("CSV", "*.csv"), ("Todos", "*.*")],
        )
        if not path:
            return
        try:
            rows = []
            int_fields = {
                "stars",
                "age_days",
                "pr_count",
                "release_count",
                "total_issues",
                "closed_issues",
                "days_since_push",
                "loc_java",
                "comments_java",
                "blank_java",
            }
            float_fields = {
                "pct_issues",
                "cbo_mean",
                "cbo_median",
                "dit_mean",
                "dit_median",
                "lcom_mean",
                "lcom_median",
            }

            col_map = {
                "repositório": "full_name",
                "repositorio": "full_name",
                "owner": "owner",
                "nome": "name",
                "estrelas": "stars",
                "linguagem primária": "language",
                "linguagem primaria": "language",
                "data criação": "createdAt",
                "data criacao": "createdAt",
                "idade (dias)": "age_days",
                "data último push": "pushedAt",
                "data ultimo push": "pushedAt",
                "dias desde último push": "days_since_push",
                "dias desde ultimo push": "days_since_push",
                "prs aceitas": "pr_count",
                "prs aceitas (merged)": "pr_count",
                "releases": "release_count",
                "total issues": "total_issues",
                "issues fechadas": "closed_issues",
                "% issues fechadas": "pct_issues",
                "loc java": "loc_java",
                "comments java": "comments_java",
                "blank java": "blank_java",
                "cbo_mean": "cbo_mean",
                "cbo_median": "cbo_median",
                "dit_mean": "dit_mean",
                "dit_median": "dit_median",
                "lcom_mean": "lcom_mean",
                "lcom_median": "lcom_median",
            }

            with open(path, "r", encoding="utf-8", errors="ignore", newline="") as f:
                reader = csv.DictReader(f)
                for i, raw in enumerate(reader, 1):
                    row = {"rank": i}
                    for csv_col, val in raw.items():
                        key = col_map.get(
                            csv_col.strip().lower(), csv_col.strip().lower()
                        )
                        if val in (None, "", "—"):
                            row[key] = None
                        elif key in int_fields:
                            try:
                                row[key] = int(float(val))
                            except Exception:
                                row[key] = None
                        elif key in float_fields:
                            try:
                                row[key] = float(val.replace(",", "."))
                            except Exception:
                                row[key] = None
                        else:
                            row[key] = val

                    if (
                        not row.get("full_name")
                        and row.get("owner")
                        and row.get("name")
                    ):
                        row["full_name"] = f"{row['owner']}/{row['name']}"

                    rows.append(row)

            if not rows:
                messagebox.showwarning("Aviso", "Nenhuma linha encontrada no CSV.")
                return

            self.all_rows = rows
            self.all_edges = []
            self.filtered_rows = None
            self.current_page = 0
            self.prog_bar["value"] = 100
            self.prog_label.config(text="100%")
            self._enable_buttons()
            self._refresh_table()
            self._update_status(
                f"{len(rows)} repositórios carregados de {os.path.basename(path)}",
                "green",
            )

        except Exception as exc:
            messagebox.showerror("Erro", f"Falha ao importar CSV:\n{exc}")

    def _download_csv(self):
        rows = self._active_rows()
        if not rows:
            messagebox.showinfo("Aviso", "Nenhum dado para exportar.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")],
            initialfile=os.path.basename(self.output_var.get()),
        )
        if not path:
            return
        try:
            if self.mode_var.get().startswith("apenas_listar") and self.all_edges:

                write_list_csv(self.all_edges, path)
            else:
                write_results_csv(rows, path)
            messagebox.showinfo("Sucesso", f"CSV salvo em:\n{path}")
        except Exception as exc:
            messagebox.showerror("Erro", f"Falha ao salvar CSV:\n{exc}")

    def _open_graphs(self):
        if not MATPLOTLIB_AVAILABLE:
            messagebox.showwarning(
                "Dependência ausente",
                "matplotlib não está instalado.\n\npip install matplotlib",
            )
            return
        rows = self._active_rows()
        if not rows:
            messagebox.showinfo("Aviso", "Nenhum dado para gráficos.")
            return
        GraphsWindow(self.root, rows)

    def _on_close(self):
        if self.is_running:
            if not messagebox.askokcancel(
                "Fechar",
                "Uma coleta está em andamento.\n\n"
                "Fechar agora vai interromper o processo.\n"
                "Os dados já coletados serão perdidos.\n\n"
                "Deseja fechar mesmo assim?",
            ):
                return

        self.stop_flag = True

        if self._executor is not None:
            try:
                self._executor.shutdown(wait=False, cancel_futures=True)
            except TypeError:
                self._executor.shutdown(wait=False)
            self._executor = None

        try:
            plt.close("all")
        except Exception:
            pass

        self.root.destroy()


class GraphsWindow(tk.Toplevel):

    RQS = [
        (
            "RQ01 – Popularidade",
            [("stars", "Estrelas", "#1565C0")],
        ),
        (
            "RQ02 – Maturidade",
            [("age_years", "Idade (anos)", "#2E7D32")],
        ),
        (
            "RQ03 – Atividade",
            [("release_count", "Releases", "#6A1B9A")],
        ),
        (
            "RQ04 – Tamanho",
            [
                ("loc_java", "LOC Java", "#E65100"),
                ("comments_java", "Linhas Comentário", "#BF360C"),
            ],
        ),
    ]

    QUALITY_MEAN = [
        ("cbo_mean", "CBO (média)", "#F44336"),
        ("dit_mean", "DIT (média)", "#3F51B5"),
        ("lcom_mean", "LCOM (média)", "#795548"),
    ]
    QUALITY_MEDIAN = [
        ("cbo_median", "CBO (mediana)", "#EF9A9A"),
        ("dit_median", "DIT (mediana)", "#9FA8DA"),
        ("lcom_median", "LCOM (mediana)", "#BCAAA4"),
    ]

    QUALITY = QUALITY_MEAN + QUALITY_MEDIAN

    def __init__(self, parent, rows):
        super().__init__(parent)
        self.title("Gráficos — Repositórios Java")
        self.geometry("1100x720")

        self.rows = []
        for r in rows:
            rc = dict(r)
            age_d = rc.get("age_days")
            rc["age_years"] = round(age_d / 365, 2) if age_d is not None else None
            self.rows.append(rc)
        self._build()

    def _paired(self, x_key, y_key):
        pairs = [
            (r[x_key], r[y_key])
            for r in self.rows
            if r.get(x_key) is not None and r.get(y_key) is not None
        ]
        if not pairs:
            return [], []
        xs, ys = zip(*pairs)
        return list(xs), list(ys)

    def _draw_scatter(self, ax, xs, ys, xlabel, ylabel, color):
        ax.scatter(xs, ys, alpha=0.40, s=14, color=color)
        if len(xs) > 2:
            try:
                m, b = np.polyfit(xs, ys, 1)
                x0, x1 = min(xs), max(xs)
                ax.plot(
                    [x0, x1],
                    [m * x0 + b, m * x1 + b],
                    color="red",
                    linewidth=1.2,
                    linestyle="--",
                )
                r = float(np.corrcoef(xs, ys)[0, 1])
                ax.set_title(
                    f"{ylabel}\nr = {r:+.3f}  (n={len(xs)})",
                    fontsize=9,
                    fontweight="bold",
                )
            except Exception:
                ax.set_title(ylabel, fontsize=9)
        else:
            ax.set_title(ylabel + "\n(dados insuficientes)", fontsize=9, color="gray")
        ax.set_xlabel(xlabel, fontsize=8)
        ax.set_ylabel(ylabel, fontsize=8)
        ax.tick_params(labelsize=7)

    def _no_data_label(self, frame):
        ttk.Label(
            frame,
            text="Dados insuficientes.\n"
            "Execute a coleta com clonagem para obter métricas CK/LOC.",
            font=("Arial", 11),
            foreground="gray",
        ).pack(expand=True)

    def _build(self):
        nb = ttk.Notebook(self)
        nb.pack(fill=tk.BOTH, expand=True)

        for rq_num, (tab_label, x_metrics) in enumerate(self.RQS, 1):
            rq_id = f"RQ0{rq_num}"
            for stat_label, quality_list in [
                ("Média", self.QUALITY_MEAN),
                ("Mediana", self.QUALITY_MEDIAN),
            ]:
                frame = ttk.Frame(nb)
                nb.add(frame, text=f"{rq_id} {stat_label}")
                self._build_rq_tab(
                    frame,
                    f"{tab_label} — {stat_label}",
                    x_metrics,
                    quality_list,
                )

        summary_frame = ttk.Frame(nb)
        nb.add(summary_frame, text="Resumo")
        self._build_summary(summary_frame)

    def _build_rq_tab(self, frame, tab_label, x_metrics, quality_list):
        n_rows = len(x_metrics)
        n_cols = 3

        has_data = any(
            self._paired(xk, qk)[0]
            for xk, _, _ in x_metrics
            for qk, _, _ in quality_list
        )
        if not has_data:
            ttk.Label(frame, text=tab_label, font=("Arial", 12, "bold")).pack(pady=8)
            self._no_data_label(frame)
            return

        fig, axes = plt.subplots(
            n_rows,
            n_cols,
            figsize=(4.5 * n_cols, 4 * n_rows),
            squeeze=False,
        )
        fig.suptitle(tab_label, fontsize=11, fontweight="bold")

        for r_idx, (xk, xl, _) in enumerate(x_metrics):
            for c_idx, (yk, yl, color) in enumerate(quality_list):
                ax = axes[r_idx][c_idx]
                xs, ys = self._paired(xk, yk)
                if xs:
                    self._draw_scatter(ax, xs, ys, xl, yl, color)
                else:
                    ax.set_visible(False)

        fig.tight_layout(rect=[0, 0, 1, 0.96])

        canvas = FigureCanvasTkAgg(fig, master=frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        plt.close(fig)

    def _build_summary(self, frame):
        import statistics as st

        stat_metrics = [
            ("Estrelas", "stars"),
            ("Idade (anos)", "age_years"),
            ("Releases", "release_count"),
            ("LOC Java", "loc_java"),
            ("Linhas Comentários", "comments_java"),
            ("CBO Média", "cbo_mean"),
            ("DIT Média", "dit_mean"),
            ("LCOM Média", "lcom_mean"),
        ]

        ttk.Label(
            frame, text="Estatísticas Descritivas", font=("Arial", 10, "bold")
        ).pack(pady=(8, 2))

        stat_tree = ttk.Treeview(
            frame,
            columns=("Métrica", "N", "Mín", "Mediana", "Média", "Máx"),
            show="headings",
            height=9,
        )
        for col, w in [
            ("Métrica", 190),
            ("N", 60),
            ("Mín", 110),
            ("Mediana", 110),
            ("Média", 110),
            ("Máx", 110),
        ]:
            stat_tree.heading(col, text=col)
            stat_tree.column(
                col, width=w, anchor=tk.CENTER if col != "Métrica" else tk.W
            )
        stat_tree.pack(fill=tk.X, padx=12)

        for label, key in stat_metrics:
            vals = [r[key] for r in self.rows if r.get(key) is not None]
            if not vals:
                stat_tree.insert("", tk.END, values=(label, 0, "—", "—", "—", "—"))
                continue
            try:
                stat_tree.insert(
                    "",
                    tk.END,
                    values=(
                        label,
                        len(vals),
                        f"{min(vals):,.2f}",
                        f"{st.median(vals):,.2f}",
                        f"{st.mean(vals):,.2f}",
                        f"{max(vals):,.2f}",
                    ),
                )
            except Exception:
                stat_tree.insert(
                    "", tk.END, values=(label, len(vals), "err", "err", "err", "err")
                )

        ttk.Label(
            frame,
            text="Correlação de Pearson (processo × qualidade)",
            font=("Arial", 10, "bold"),
        ).pack(pady=(10, 2))

        corr_cols = ("Processo", "vs CBO  (r)", "vs DIT  (r)", "vs LCOM (r)")
        corr_tree = ttk.Treeview(frame, columns=corr_cols, show="headings", height=5)
        for col, w in zip(corr_cols, [190, 120, 120, 120]):
            corr_tree.heading(col, text=col)
            corr_tree.column(
                col, width=w, anchor=tk.CENTER if col != "Processo" else tk.W
            )
        corr_tree.pack(fill=tk.X, padx=12, pady=(0, 12))

        process_metrics = [
            ("Estrelas", "stars"),
            ("Idade (anos)", "age_years"),
            ("Releases", "release_count"),
            ("LOC Java", "loc_java"),
            ("Linhas Comentários", "comments_java"),
        ]
        for p_label, p_key in process_metrics:
            row_vals = [p_label]
            for q_key, _, _ in self.QUALITY:
                xs, ys = self._paired(p_key, q_key)
                if len(xs) > 2:
                    try:
                        r = float(np.corrcoef(xs, ys)[0, 1])
                        row_vals.append(f"{r:+.4f} (n={len(xs)})")
                    except Exception:
                        row_vals.append("err")
                else:
                    row_vals.append(f"— (n={len(xs)})")
            corr_tree.insert("", tk.END, values=tuple(row_vals))


def main():
    root = tk.Tk()
    app = JavaRepoAnalyzerGUI(root)
    root.mainloop()
    import sys

    sys.exit(0)


if __name__ == "__main__":
    main()
