import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime
import time
import threading
import json
import os
from github_utils import (
    calculate_age_in_days,
    calculate_days_since_push,
    calculate_closed_issues_ratio,
    format_age,
    fetch_repositories,
    validate_token,
    export_to_csv,
)

try:
    import matplotlib
    matplotlib.use("TkAgg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False

_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(_DIR, ".github_api_cache.json")
SESSION_FILE = os.path.join(_DIR, ".github_session.json")
CACHE_TTL = 86400  # 24 horas em segundos


class GitHubAnalyzerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Análise de Repositórios Populares - GitHub")
        self.root.geometry("1200x700")
        self.root.resizable(True, True)

        self.token = tk.StringVar()
        self.token.trace("w", self.on_token_change)
        self.all_repos = []
        self.filtered_repos = None
        self.current_page = 0
        self.items_per_page = 20
        self.is_fetching = False
        self.stop_collection = False
        self.progress_value = 0
        self.page_input = tk.StringVar(value="0")
        self.filter_visible = False
        self._cache = self._load_cache()

        self.setup_ui()


    def setup_ui(self):
        # token / controles
        top_frame = ttk.Frame(self.root, padding="10")
        top_frame.pack(fill=tk.X)

        ttk.Label(top_frame, text="GitHub Token:", font=("Arial", 10, "bold")).pack(
            side=tk.LEFT, padx=5
        )
        ttk.Entry(top_frame, textvariable=self.token, width=50, show="*").pack(
            side=tk.LEFT, padx=5
        )

        self.btn_start = ttk.Button(
            top_frame, text="▶ Iniciar Coleta", command=self.start_collection,
            state=tk.DISABLED,
        )
        self.btn_start.pack(side=tk.LEFT, padx=10)

        self.btn_stop = ttk.Button(
            top_frame, text="⏹ Encerrar Processo",
            command=self.stop_collection_process, state=tk.DISABLED,
        )
        self.btn_stop.pack(side=tk.LEFT, padx=5)

        # progresso
        self._progress_frame = ttk.Frame(self.root, padding="10")
        self._progress_frame.pack(fill=tk.X)

        ttk.Label(self._progress_frame, text="Progresso:", font=("Arial", 9)).pack(
            side=tk.LEFT, padx=5
        )
        self.progress_bar = ttk.Progressbar(
            self._progress_frame, length=480, mode="determinate"
        )
        self.progress_bar.pack(side=tk.LEFT, padx=5)

        self.progress_label = ttk.Label(
            self._progress_frame, text="0%", font=("Arial", 9, "bold")
        )
        self.progress_label.pack(side=tk.LEFT, padx=5)

        self.btn_download = ttk.Button(
            self._progress_frame, text="💾 Baixar CSV",
            command=self.download_csv, state=tk.DISABLED,
        )
        self.btn_download.pack(side=tk.LEFT, padx=8)

        self.btn_graphs = ttk.Button(
            self._progress_frame, text="📊 Ver Gráficos",
            command=self.open_graphs_window, state=tk.DISABLED,
        )
        self.btn_graphs.pack(side=tk.LEFT, padx=4)

        self.btn_filter_toggle = ttk.Button(
            self._progress_frame, text="🔍 Filtros",
            command=self._toggle_filters, state=tk.DISABLED,
        )
        self.btn_filter_toggle.pack(side=tk.LEFT, padx=4)

        # painel de filtros
        self.filter_frame = ttk.LabelFrame(
            self.root, text="Filtros Avançados", padding="8"
        )

        row1 = ttk.Frame(self.filter_frame)
        row1.pack(fill=tk.X, pady=2)

        ttk.Label(row1, text="Nome contém:", font=("Arial", 9)).pack(side=tk.LEFT, padx=(0, 3))
        self.filter_name = tk.StringVar()
        ttk.Entry(row1, textvariable=self.filter_name, width=18).pack(side=tk.LEFT, padx=(0, 14))

        ttk.Label(row1, text="Linguagem:", font=("Arial", 9)).pack(side=tk.LEFT, padx=(0, 3))
        self.filter_lang = tk.StringVar(value="Todas")
        self.combo_lang_filter = ttk.Combobox(
            row1, textvariable=self.filter_lang, values=["Todas"],
            width=14, state="readonly",
        )
        self.combo_lang_filter.pack(side=tk.LEFT, padx=(0, 14))

        ttk.Label(row1, text="Idade (dias):", font=("Arial", 9)).pack(side=tk.LEFT, padx=(0, 3))
        self.filter_age_min = tk.StringVar()
        ttk.Entry(row1, textvariable=self.filter_age_min, width=7).pack(side=tk.LEFT)
        ttk.Label(row1, text="–").pack(side=tk.LEFT, padx=2)
        self.filter_age_max = tk.StringVar()
        ttk.Entry(row1, textvariable=self.filter_age_max, width=7).pack(side=tk.LEFT, padx=(0, 14))

        ttk.Label(row1, text="PRs:", font=("Arial", 9)).pack(side=tk.LEFT, padx=(0, 3))
        self.filter_prs_min = tk.StringVar()
        ttk.Entry(row1, textvariable=self.filter_prs_min, width=7).pack(side=tk.LEFT)
        ttk.Label(row1, text="–").pack(side=tk.LEFT, padx=2)
        self.filter_prs_max = tk.StringVar()
        ttk.Entry(row1, textvariable=self.filter_prs_max, width=7).pack(side=tk.LEFT)

        row2 = ttk.Frame(self.filter_frame)
        row2.pack(fill=tk.X, pady=2)

        ttk.Label(row2, text="Releases:", font=("Arial", 9)).pack(side=tk.LEFT, padx=(0, 3))
        self.filter_rel_min = tk.StringVar()
        ttk.Entry(row2, textvariable=self.filter_rel_min, width=7).pack(side=tk.LEFT)
        ttk.Label(row2, text="–").pack(side=tk.LEFT, padx=2)
        self.filter_rel_max = tk.StringVar()
        ttk.Entry(row2, textvariable=self.filter_rel_max, width=7).pack(side=tk.LEFT, padx=(0, 14))

        ttk.Label(row2, text="Issues % fechadas:", font=("Arial", 9)).pack(side=tk.LEFT, padx=(0, 3))
        self.filter_issues_min = tk.StringVar()
        ttk.Entry(row2, textvariable=self.filter_issues_min, width=7).pack(side=tk.LEFT)
        ttk.Label(row2, text="–").pack(side=tk.LEFT, padx=2)
        self.filter_issues_max = tk.StringVar()
        ttk.Entry(row2, textvariable=self.filter_issues_max, width=7).pack(side=tk.LEFT, padx=(0, 14))

        ttk.Label(row2, text="Dias desde push:", font=("Arial", 9)).pack(side=tk.LEFT, padx=(0, 3))
        self.filter_days_min = tk.StringVar()
        ttk.Entry(row2, textvariable=self.filter_days_min, width=7).pack(side=tk.LEFT)
        ttk.Label(row2, text="–").pack(side=tk.LEFT, padx=2)
        self.filter_days_max = tk.StringVar()
        ttk.Entry(row2, textvariable=self.filter_days_max, width=7).pack(side=tk.LEFT, padx=(0, 18))

        ttk.Button(row2, text="✔ Aplicar", command=self._apply_filters).pack(side=tk.LEFT, padx=4)
        ttk.Button(row2, text="✖ Limpar", command=self._clear_filters).pack(side=tk.LEFT, padx=4)

        self.filter_status_label = ttk.Label(
            self.filter_frame, text="", font=("Arial", 9, "italic"), foreground="gray"
        )
        self.filter_status_label.pack(anchor=tk.W, pady=(2, 0))

        # tabela
        table_frame = ttk.Frame(self.root, padding="10")
        table_frame.pack(fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(table_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        columns = ("#", "Repositório", "Linguagem", "Idade", "PRs",
                   "Releases", "Issues %", "Dias Atualiz.")
        self.tree = ttk.Treeview(
            table_frame, columns=columns, show="headings",
            yscrollcommand=scrollbar.set, height=20,
        )
        scrollbar.config(command=self.tree.yview)

        for col, w, anchor in [
            ("#", 40, tk.CENTER), ("Repositório", 300, tk.W),
            ("Linguagem", 100, tk.CENTER), ("Idade", 100, tk.CENTER),
            ("PRs", 80, tk.CENTER), ("Releases", 80, tk.CENTER),
            ("Issues %", 90, tk.CENTER), ("Dias Atualiz.", 110, tk.CENTER),
        ]:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=w, anchor=anchor)

        self.tree.pack(fill=tk.BOTH, expand=True)

        # navegação 
        nav_frame = ttk.Frame(self.root, padding="10")
        nav_frame.pack(fill=tk.X)

        self.btn_prev = ttk.Button(
            nav_frame, text="◀ Anterior", command=self.prev_page, state=tk.DISABLED
        )
        self.btn_prev.pack(side=tk.LEFT, padx=5)

        ttk.Label(nav_frame, text="Página", font=("Arial", 9)).pack(side=tk.LEFT, padx=(20, 5))

        self.page_entry = ttk.Entry(
            nav_frame, textvariable=self.page_input, width=5,
            justify=tk.CENTER, font=("Arial", 9),
        )
        self.page_entry.pack(side=tk.LEFT)
        self.page_entry.bind("<Return>", self.goto_page_from_entry)

        self.page_total_label = ttk.Label(nav_frame, text="de 0", font=("Arial", 9, "bold"))
        self.page_total_label.pack(side=tk.LEFT, padx=(5, 20))

        self.btn_next = ttk.Button(
            nav_frame, text="Próxima ▶", command=self.next_page, state=tk.DISABLED
        )
        self.btn_next.pack(side=tk.LEFT, padx=5)

        self.status_label = ttk.Label(
            nav_frame, text="Aguardando início...", font=("Arial", 9), foreground="blue"
        )
        self.status_label.pack(side=tk.RIGHT, padx=10)

    # cache

    def _load_cache(self):
        try:
            if os.path.exists(CACHE_FILE):
                with open(CACHE_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    def _save_cache(self):
        try:
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(self._cache, f)
        except Exception as e:
            print(f"Cache: erro ao salvar: {e}")

    def _cache_key(self, cursor, page_size):
        return f"{cursor or 'start'}|{page_size}"

    def _get_from_cache(self, cursor, page_size):
        key = self._cache_key(cursor, page_size)
        entry = self._cache.get(key)
        if entry and (time.time() - entry["ts"]) < CACHE_TTL:
            return entry["data"]
        return None

    def _put_in_cache(self, cursor, page_size, data):
        key = self._cache_key(cursor, page_size)
        self._cache[key] = {"data": data, "ts": time.time()}
        self._save_cache()

    # retomar sessão

    def _save_session(self, cursor, repos, total_fetched):
        try:
            session = {
                "cursor": cursor,
                "repos": repos,
                "total_fetched": total_fetched,
                "timestamp": time.time(),
            }
            with open(SESSION_FILE, "w", encoding="utf-8") as f:
                json.dump(session, f)
        except Exception as e:
            print(f"Sessão: erro ao salvar: {e}")

    def _load_session(self):
        try:
            if os.path.exists(SESSION_FILE):
                with open(SESSION_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return None

    def _clear_session(self):
        try:
            if os.path.exists(SESSION_FILE):
                os.remove(SESSION_FILE)
        except Exception:
            pass

    def _has_valid_session(self):
        session = self._load_session()
        if not session:
            return False
        age = time.time() - session.get("timestamp", 0)
        repos_count = len(session.get("repos", []))
        return age < CACHE_TTL and repos_count > 0 and repos_count < 1000

    #filtros

    def _toggle_filters(self):
        if self.filter_visible:
            self.filter_frame.pack_forget()
            self.filter_visible = False
            self.btn_filter_toggle.config(text="🔍 Filtros")
        else:
            self.filter_frame.pack(
                fill=tk.X, padx=10, pady=(0, 4),
                after=self._progress_frame,
            )
            self.filter_visible = True
            self.btn_filter_toggle.config(text="🔍 Fechar Filtros")

    def _update_lang_filter_options(self):
        langs = sorted({
            (r["node"]["primaryLanguage"]["name"] if r["node"]["primaryLanguage"] else "N/A")
            for r in self.all_repos
        })
        self.combo_lang_filter["values"] = ["Todas"] + langs

    @staticmethod
    def _safe_int(val, default):
        try:
            return int(val.strip())
        except Exception:
            return default

    @staticmethod
    def _safe_float(val, default):
        try:
            return float(val.strip())
        except Exception:
            return default

    def _apply_filters(self):
        if not self.all_repos:
            return

        name_f = self.filter_name.get().strip().lower()
        lang_f = self.filter_lang.get().strip()
        age_min = self._safe_int(self.filter_age_min.get(), 0)
        age_max = self._safe_int(self.filter_age_max.get(), 10 ** 9)
        prs_min = self._safe_int(self.filter_prs_min.get(), 0)
        prs_max = self._safe_int(self.filter_prs_max.get(), 10 ** 9)
        rel_min = self._safe_int(self.filter_rel_min.get(), 0)
        rel_max = self._safe_int(self.filter_rel_max.get(), 10 ** 9)
        iss_min = self._safe_float(self.filter_issues_min.get(), 0.0)
        iss_max = self._safe_float(self.filter_issues_max.get(), 100.0)
        days_min = self._safe_int(self.filter_days_min.get(), 0)
        days_max = self._safe_int(self.filter_days_max.get(), 10 ** 9)

        result = []
        for repo in self.all_repos:
            node = repo["node"]
            full_name = f"{node['owner']['login']}/{node['name']}".lower()
            lang = node["primaryLanguage"]["name"] if node["primaryLanguage"] else "N/A"
            age = calculate_age_in_days(node["createdAt"])
            prs = node["pullRequests"]["totalCount"]
            releases = node["releases"]["totalCount"]
            total_iss = node["issues"]["totalCount"]
            closed_iss = node["closedIssues"]["totalCount"]
            iss_pct = calculate_closed_issues_ratio(closed_iss, total_iss)
            days = max(0, calculate_days_since_push(node["pushedAt"]))

            if name_f and name_f not in full_name:
                continue
            if lang_f and lang_f != "Todas" and lang != lang_f:
                continue
            if not (age_min <= age <= age_max):
                continue
            if not (prs_min <= prs <= prs_max):
                continue
            if not (rel_min <= releases <= rel_max):
                continue
            if not (iss_min <= iss_pct <= iss_max):
                continue
            if not (days_min <= days <= days_max):
                continue
            result.append(repo)

        self.filtered_repos = result
        self.current_page = 0
        self.display_current_page()

        total = len(self.all_repos)
        count = len(result)
        color = "green" if count == total else "orange"
        self.filter_status_label.config(
            text=f"Filtros ativos: {count} de {total} repositórios", foreground=color
        )

    def _clear_filters(self):
        for var in (
            self.filter_name, self.filter_age_min, self.filter_age_max,
            self.filter_prs_min, self.filter_prs_max, self.filter_rel_min,
            self.filter_rel_max, self.filter_issues_min, self.filter_issues_max,
            self.filter_days_min, self.filter_days_max,
        ):
            var.set("")
        self.filter_lang.set("Todas")
        self.filtered_repos = None
        self.current_page = 0
        self.filter_status_label.config(text="")
        self.display_current_page()

    # helpers

    def _active_repos(self):
        return self.filtered_repos if self.filtered_repos is not None else self.all_repos

    def on_token_change(self, *args):
        state = tk.NORMAL if self.token.get().strip() else tk.DISABLED
        self.btn_start.config(state=state)

    # coleta de dados

    def start_collection(self):
        if self.is_fetching:
            return

        token = self.token.get().strip()
        self.status_label.config(text="Validando token...", foreground="orange")
        self.root.update()

        if not validate_token(token):
            messagebox.showerror("Erro", "Token inválido! Verifique e tente novamente.")
            self.status_label.config(text="Token inválido", foreground="red")
            return

        # retomada de sessão anterior
        resume_cursor = None
        resume_repos = []
        if self._has_valid_session():
            session = self._load_session()
            count = len(session["repos"])
            answer = messagebox.askyesno(
                "Retomar coleta",
                f"Foi encontrada uma coleta anterior interrompida com "
                f"{count} repositórios já coletados.\n\n"
                f"Deseja continuar de onde parou?",
            )
            if answer:
                resume_cursor = session["cursor"]
                resume_repos = session["repos"]

        self.is_fetching = True
        self.stop_collection = False
        self.all_repos = list(resume_repos)
        self.filtered_repos = None
        self.current_page = 0
        self.btn_start.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        self.btn_download.config(state=tk.DISABLED)
        self.btn_graphs.config(state=tk.DISABLED)
        self.btn_filter_toggle.config(state=tk.DISABLED)
        self.progress_bar["value"] = (len(resume_repos) / 1000) * 100
        self.progress_label.config(text=f"{int(len(resume_repos) / 10)}%")

        thread = threading.Thread(
            target=self.fetch_all_repositories,
            args=(token, resume_cursor, len(resume_repos)),
            daemon=True,
        )
        thread.start()

    def fetch_all_repositories(self, token, start_cursor=None, start_total=0):
        cursor = start_cursor
        page_size = 10
        total_fetched = start_total
        max_repos = 1000

        self.update_status(f"Coletando {max_repos} repositórios...", "blue")

        while total_fetched < max_repos and not self.stop_collection:
            page_num = (total_fetched // page_size) + 1

            # verificar cache
            cached = self._get_from_cache(cursor, page_size)
            if cached:
                data = cached
                self.update_status(
                    f"Página {page_num}/100 (cache)...", "blue"
                )
            else:
                self.update_status(f"Buscando página {page_num}/100...", "blue")
                data = fetch_repositories(token, cursor, page_size)
                if data and "data" in data and "errors" not in data:
                    self._put_in_cache(cursor, page_size, data)

            if not data or "data" not in data:
                self.update_status(
                    f"Erro ao buscar dados. Coletados: {len(self.all_repos)}", "red"
                )
                self.root.after(
                    0,
                    lambda: messagebox.showerror(
                        "Erro de Conexão",
                        f"Não foi possível completar a coleta.\n\n"
                        f"Repositórios coletados: {len(self.all_repos)}\n"
                        f"Meta: {max_repos}\n\n"
                        f"Possíveis causas:\n"
                        f"• Problemas de conexão com internet\n"
                        f"• Firewall bloqueando acesso ao GitHub\n"
                        f"• Timeout na requisição\n\n"
                        f"Os dados já coletados estão disponíveis.",
                    ),
                )
                break

            if "errors" in data:
                self.update_status(f"Erro GraphQL: {data['errors']}", "red")
                break

            search_data = data["data"]["search"]
            repos = search_data["edges"]
            if not repos:
                break

            self.all_repos.extend(repos)
            total_fetched += len(repos)

            self.update_progress((total_fetched / max_repos) * 100)

            current_page_end = (self.current_page + 1) * self.items_per_page
            if total_fetched <= self.items_per_page or total_fetched >= current_page_end:
                self.root.after(0, self.display_current_page)

            page_info = search_data["pageInfo"]
            if (
                not page_info["hasNextPage"]
                or total_fetched >= max_repos
                or self.stop_collection
            ):
                break

            cursor = page_info["endCursor"]

            # salvar sessão a cada página
            if not self.stop_collection:
                self._save_session(cursor, self.all_repos, total_fetched)

            time.sleep(2)

        self.is_fetching = False
        self.root.after(0, lambda: self.btn_stop.config(state=tk.DISABLED))

        if self.stop_collection:
            status_msg = f"⏹ Processo encerrado: {len(self.all_repos)} repositórios coletados"
            status_color = "orange"
        elif len(self.all_repos) >= max_repos:
            status_msg = f"✓ Coleta concluída! {len(self.all_repos)} repositórios"
            status_color = "green"
            self._clear_session()
        elif len(self.all_repos) > 0:
            status_msg = f"⚠️ Coleta parcial: {len(self.all_repos)} repositórios coletados"
            status_color = "orange"
        else:
            status_msg = "❌ Nenhum repositório foi coletado"
            status_color = "red"

        self.update_status(status_msg, status_color)
        self.update_progress(
            100 if len(self.all_repos) >= max_repos
            else (len(self.all_repos) / max_repos) * 100
        )

        if len(self.all_repos) > 0:
            self.root.after(0, self.enable_download)

        self.root.after(0, self.display_current_page)

    def update_progress(self, value):
        def _u():
            self.progress_bar["value"] = value
            self.progress_label.config(text=f"{int(value)}%")
        self.root.after(0, _u)

    def update_status(self, message, color):
        def _u():
            self.status_label.config(text=message, foreground=color)
        self.root.after(0, _u)

    # tabelas

    def display_current_page(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        repos = self._active_repos()

        if not repos:
            self.page_input.set("0")
            self.page_total_label.config(text="de 0")
            self.btn_prev.config(state=tk.DISABLED)
            self.btn_next.config(state=tk.DISABLED)
            return

        start_idx = self.current_page * self.items_per_page
        end_idx = min(start_idx + self.items_per_page, len(repos))

        for i in range(start_idx, end_idx):
            node = repos[i]["node"]
            name = f"{node['owner']['login']}/{node['name']}"
            language = node["primaryLanguage"]["name"] if node["primaryLanguage"] else "N/A"
            age = format_age(calculate_age_in_days(node["createdAt"]))
            prs = node["pullRequests"]["totalCount"]
            releases = node["releases"]["totalCount"]
            total_iss = node["issues"]["totalCount"]
            closed_iss = node["closedIssues"]["totalCount"]
            issues_ratio = calculate_closed_issues_ratio(closed_iss, total_iss)
            days_since = calculate_days_since_push(node["pushedAt"])

            if days_since == 0:
                days_display = "Hoje"
            elif days_since == 1:
                days_display = "1d"
            else:
                days_display = f"{days_since}d"

            self.tree.insert(
                "", tk.END,
                values=(i + 1, name, language, age, prs, releases,
                        f"{issues_ratio:.1f}%", days_display),
            )

        total_pages = (len(repos) + self.items_per_page - 1) // self.items_per_page
        self.page_input.set(str(self.current_page + 1))
        self.page_total_label.config(text=f"de {total_pages}")
        self.btn_prev.config(state=tk.NORMAL if self.current_page > 0 else tk.DISABLED)
        self.btn_next.config(state=tk.NORMAL if end_idx < len(repos) else tk.DISABLED)
        self.root.update_idletasks()

    def prev_page(self):
        if self.current_page > 0:
            self.current_page -= 1
            self.display_current_page()

    def goto_page_from_entry(self, event=None):
        try:
            page_num = int(self.page_input.get())
            repos = self._active_repos()
            if not repos:
                self.page_input.set("0")
                messagebox.showwarning("Aviso", "Nenhum dado carregado ainda!")
                return
            total_pages = (len(repos) + self.items_per_page - 1) // self.items_per_page
            if page_num < 1 or page_num > total_pages:
                self.page_input.set(str(self.current_page + 1))
                messagebox.showwarning(
                    "Página Inválida",
                    f"Por favor, digite um número entre 1 e {total_pages}.",
                )
                return
            self.current_page = page_num - 1
            self.display_current_page()
        except ValueError:
            self.page_input.set(str(self.current_page + 1))
            messagebox.showwarning("Entrada Inválida", "Por favor, digite um número válido.")

    def next_page(self):
        repos = self._active_repos()
        total_pages = (len(repos) + self.items_per_page - 1) // self.items_per_page
        if self.current_page < total_pages - 1:
            self.current_page += 1
            self.display_current_page()

    def enable_download(self):
        self.btn_download.config(state=tk.NORMAL)
        self.btn_graphs.config(state=tk.NORMAL)
        self.btn_filter_toggle.config(state=tk.NORMAL)
        self.btn_start.config(state=tk.NORMAL)
        self._update_lang_filter_options()

    def stop_collection_process(self):
        if self.is_fetching:
            self.stop_collection = True
            self.btn_stop.config(state=tk.DISABLED)
            self.update_status("🛑 Encerrando coleta...", "orange")

    def download_csv(self):
        if not self.all_repos:
            messagebox.showwarning("Aviso", "Nenhum dado para exportar!")
            return

        filename = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile=f"github_repos_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        )
        if not filename:
            return

        try:
            if export_to_csv(self.all_repos, filename):
                messagebox.showinfo("Sucesso", f"Dados salvos em:\n{filename}")
                self.update_status("✓ CSV exportado com sucesso!", "green")
            else:
                messagebox.showerror("Erro", "Erro ao salvar arquivo")
                self.update_status("Erro ao exportar CSV", "red")
        except Exception as e:
            messagebox.showerror("Erro", f"Erro ao salvar arquivo:\n{str(e)}")

    # gráficos

    def open_graphs_window(self):
        if not self.all_repos:
            messagebox.showwarning("Aviso", "Nenhum dado para visualizar!")
            return
        if not MATPLOTLIB_AVAILABLE:
            messagebox.showerror(
                "Erro",
                "matplotlib não está instalado.\nInstale com:\n  pip install matplotlib",
            )
            return

        data = self._compute_graph_data()

        win = tk.Toplevel(self.root)
        win.title(f"Visualização de Gráficos — {len(self.all_repos)} repositórios")
        win.geometry("1150x720")
        win.resizable(True, True)

        notebook = ttk.Notebook(win)
        notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        tab1 = ttk.Frame(notebook)
        notebook.add(tab1, text="RQ01 – Idade")
        self._make_stats_tab(
            tab1,
            "RQ01 – Sistemas populares são maduros/antigos?\nIdade dos Repositórios",
            data["stats_ages"], "Dias", "#4C72B0",
        )

        tab2 = ttk.Frame(notebook)
        notebook.add(tab2, text="RQ02 – Pull Requests")
        self._make_stats_tab(
            tab2,
            "RQ02 – Sistemas populares recebem muita contribuição externa?\nPull Requests Aceitas",
            data["stats_prs"], "Quantidade de PRs", "#DD8452",
        )

        tab3 = ttk.Frame(notebook)
        notebook.add(tab3, text="RQ03 – Releases")
        self._make_stats_tab(
            tab3,
            "RQ03 – Sistemas populares lançam releases com frequência?\nNúmero de Releases",
            data["stats_releases"], "Quantidade de Releases", "#55A868",
        )

        tab4 = ttk.Frame(notebook)
        notebook.add(tab4, text="RQ04 – Atualização")
        self._make_stats_tab(
            tab4,
            "RQ04 – Sistemas populares são atualizados com frequência?\nDias desde Último Push",
            data["stats_push"], "Dias", "#C44E52",
        )

        tab5 = ttk.Frame(notebook)
        notebook.add(tab5, text="RQ05 – Linguagens")
        self._make_pie_tab(
            tab5,
            "RQ05 – Sistemas populares são escritos nas linguagens mais populares?\nTop 10 Linguagens",
            data["sorted_langs"], len(self.all_repos),
        )

        tab6 = ttk.Frame(notebook)
        notebook.add(tab6, text="RQ06 – Issues")
        self._make_stats_tab(
            tab6,
            "RQ06 – Sistemas populares possuem alto percentual de issues fechadas?\nPercentual de Issues Fechadas",
            data["stats_issues"], "% Issues Fechadas", "#8172B2", is_pct=True,
        )

        tab7 = ttk.Frame(notebook)
        notebook.add(tab7, text="RQ07 – Comparação")
        self._make_comparison_tab(tab7, data)

        def on_close():
            plt.close("all")
            win.destroy()

        win.protocol("WM_DELETE_WINDOW", on_close)

    def _compute_graph_data(self):
        repos = self.all_repos

        ages = [calculate_age_in_days(r["node"]["createdAt"]) for r in repos]
        prs = [r["node"]["pullRequests"]["totalCount"] for r in repos]
        releases_list = [r["node"]["releases"]["totalCount"] for r in repos]
        days_push = [max(0, calculate_days_since_push(r["node"]["pushedAt"])) for r in repos]

        issues_ratios = []
        for r in repos:
            node = r["node"]
            total = node["issues"]["totalCount"]
            closed = node["closedIssues"]["totalCount"]
            issues_ratios.append(calculate_closed_issues_ratio(closed, total))

        lang_count = {}
        for r in repos:
            lang = r["node"]["primaryLanguage"]
            lang_name = lang["name"] if lang else "N/A"
            lang_count[lang_name] = lang_count.get(lang_name, 0) + 1

        sorted_langs = sorted(lang_count.items(), key=lambda x: x[1], reverse=True)

        def stats(data):
            s = sorted(data)
            n = len(s)
            return {"mean": sum(data) / n, "median": s[n // 2],
                    "min": min(data), "max": max(data)}

        lang_details = {}
        for lang_name, _ in sorted_langs:
            lang_repos = [
                r for r in repos
                if (r["node"]["primaryLanguage"] and r["node"]["primaryLanguage"]["name"] == lang_name)
                or (not r["node"]["primaryLanguage"] and lang_name == "N/A")
            ]
            if not lang_repos:
                continue
            l_prs = [r["node"]["pullRequests"]["totalCount"] for r in lang_repos]
            l_releases = [r["node"]["releases"]["totalCount"] for r in lang_repos]
            l_push = [max(0, calculate_days_since_push(r["node"]["pushedAt"])) for r in lang_repos]
            l_issues = []
            for r in lang_repos:
                node = r["node"]
                total = node["issues"]["totalCount"]
                closed = node["closedIssues"]["totalCount"]
                l_issues.append(calculate_closed_issues_ratio(closed, total))
            l_ages = [calculate_age_in_days(r["node"]["createdAt"]) for r in lang_repos]
            lang_details[lang_name] = {
                "count": len(lang_repos),
                "stats_prs": stats(l_prs),
                "stats_releases": stats(l_releases),
                "stats_push": stats(l_push),
                "stats_issues": stats(l_issues),
                "stats_ages": stats(l_ages),
            }

        return {
            "ages": ages, "prs": prs, "releases": releases_list,
            "days_push": days_push, "issues_ratios": issues_ratios,
            "lang_count": lang_count, "sorted_langs": sorted_langs,
            "all_lang_names": [l[0] for l in sorted_langs],
            "lang_details": lang_details,
            "stats_ages": stats(ages), "stats_prs": stats(prs),
            "stats_releases": stats(releases_list), "stats_push": stats(days_push),
            "stats_issues": stats(issues_ratios),
        }

    @staticmethod
    def _fmt_val(val, is_pct=False):
        if is_pct:
            return f"{val:.1f}%"
        return f"{int(round(val)):,}" if val == round(val) else f"{val:,.1f}"

    def _make_stats_tab(self, parent, title, stats_dict, ylabel, color, is_pct=False):
        fig, ax = plt.subplots(figsize=(9, 5))
        labels = ["Média", "Mediana", "Mínimo", "Máximo"]
        values = [stats_dict["mean"], stats_dict["median"],
                  stats_dict["min"], stats_dict["max"]]

        bars = ax.bar(labels, values, color=color, edgecolor="white", linewidth=1.2, width=0.5)
        ax.set_title(title, fontsize=12, pad=15)
        ax.set_ylabel(ylabel, fontsize=10)
        ax.set_xlabel("Estatística", fontsize=10)
        ax.set_ylim(bottom=0)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

        for bar, val in zip(bars, values):
            offset = max(bar.get_height() * 0.015, ax.get_ylim()[1] * 0.01)
            ax.text(
                bar.get_x() + bar.get_width() / 2.0,
                bar.get_height() + offset,
                self._fmt_val(val, is_pct),
                ha="center", va="bottom", fontsize=11, fontweight="bold",
            )

        fig.tight_layout(pad=2.5)
        canvas = FigureCanvasTkAgg(fig, parent)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

    def _make_pie_tab(self, parent, title, sorted_langs, total):
        top10 = sorted_langs[:10]
        labels = [l[0] for l in top10]
        sizes = [l[1] for l in top10]
        other = total - sum(sizes)
        if other > 0:
            labels.append("Outros")
            sizes.append(other)

        fig, ax = plt.subplots(figsize=(10, 6))

        tab10 = list(plt.cm.tab10.colors[:10])
        colors = tab10[: len(top10)]
        if other > 0:
            colors.append("#999999")

        wedges, texts, autotexts = ax.pie(
            sizes, labels=labels,
            autopct=lambda pct: f"{pct:.1f}%" if pct > 2 else "",
            startangle=90, colors=colors, pctdistance=0.8,
        )
        for text in texts:
            text.set_fontsize(9)
        for autotext in autotexts:
            autotext.set_fontsize(8)
            autotext.set_fontweight("bold")

        ax.set_title(title, fontsize=12, pad=20)
        legend_labels = [
            f"{l} — {s} repos ({s / total * 100:.1f}%)"
            for l, s in zip(labels, sizes)
        ]
        ax.legend(wedges, legend_labels, loc="lower center",
                  bbox_to_anchor=(0.5, -0.18), ncol=2, fontsize=8)
        fig.tight_layout()

        canvas = FigureCanvasTkAgg(fig, parent)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

    def _make_comparison_tab(self, parent, data):
        lang_names = data["all_lang_names"]

        ctrl_frame = ttk.Frame(parent, padding="8")
        ctrl_frame.pack(fill=tk.X)

        ttk.Label(ctrl_frame, text="RQ07 – Comparar Linguagens:",
                  font=("Arial", 10, "bold")).pack(side=tk.LEFT, padx=5)

        lang_a_var = tk.StringVar(value=lang_names[0] if lang_names else "")
        lang_b_var = tk.StringVar(value=lang_names[1] if len(lang_names) > 1 else "")

        ttk.Label(ctrl_frame, text="Linguagem A:", font=("Arial", 9)).pack(side=tk.LEFT, padx=(15, 2))
        ttk.Combobox(ctrl_frame, textvariable=lang_a_var, values=lang_names,
                     width=18, state="readonly").pack(side=tk.LEFT, padx=2)

        ttk.Label(ctrl_frame, text="vs  Linguagem B:", font=("Arial", 9)).pack(side=tk.LEFT, padx=(12, 2))
        ttk.Combobox(ctrl_frame, textvariable=lang_b_var, values=lang_names,
                     width=18, state="readonly").pack(side=tk.LEFT, padx=2)

        graph_frame = ttk.Frame(parent)
        graph_frame.pack(fill=tk.BOTH, expand=True)

        canvas_holder = {"canvas": None, "fig": None}

        def _clear_canvas():
            if canvas_holder["canvas"]:
                canvas_holder["canvas"].get_tk_widget().destroy()
                plt.close(canvas_holder["fig"])
                canvas_holder["canvas"] = None
                canvas_holder["fig"] = None

        def _embed(fig):
            canvas = FigureCanvasTkAgg(fig, graph_frame)
            canvas.draw()
            canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
            canvas_holder["canvas"] = canvas
            canvas_holder["fig"] = fig

        def update_comparison():
            lang_a = lang_a_var.get()
            lang_b = lang_b_var.get()
            if lang_a == lang_b:
                messagebox.showwarning("Aviso", "Selecione linguagens diferentes para comparar!")
                return
            if lang_a not in data["lang_details"] or lang_b not in data["lang_details"]:
                messagebox.showwarning("Aviso", "Dados insuficientes para uma das linguagens.")
                return

            _clear_canvas()
            da = data["lang_details"][lang_a]
            db = data["lang_details"][lang_b]
            col_a, col_b = "#4C72B0", "#DD8452"

            metrics = [
                ("PRs — Média", da["stats_prs"]["mean"], db["stats_prs"]["mean"]),
                ("PRs — Mediana", da["stats_prs"]["median"], db["stats_prs"]["median"]),
                ("Releases — Média", da["stats_releases"]["mean"], db["stats_releases"]["mean"]),
                ("Releases — Mediana", da["stats_releases"]["median"], db["stats_releases"]["median"]),
                ("Dias desde Push — Média", da["stats_push"]["mean"], db["stats_push"]["mean"]),
                ("Issues Fechadas % — Média", da["stats_issues"]["mean"], db["stats_issues"]["mean"]),
            ]

            fig, axes = plt.subplots(2, 3, figsize=(12, 7))
            fig.suptitle(f"RQ07 – Comparação: {lang_a} vs {lang_b}",
                         fontsize=13, fontweight="bold")

            for idx, (ax, (metric_name, val_a, val_b)) in enumerate(zip(axes.flat, metrics)):
                is_pct = idx == 5
                bars = ax.bar([lang_a, lang_b], [val_a, val_b],
                              color=[col_a, col_b], width=0.5, edgecolor="white")
                ax.set_title(metric_name, fontsize=10)
                ax.set_ylim(bottom=0)
                ax.spines["top"].set_visible(False)
                ax.spines["right"].set_visible(False)
                for bar, val in zip(bars, [val_a, val_b]):
                    offset = max(bar.get_height() * 0.02, ax.get_ylim()[1] * 0.01)
                    ax.text(bar.get_x() + bar.get_width() / 2.0,
                            bar.get_height() + offset,
                            self._fmt_val(val, is_pct),
                            ha="center", va="bottom", fontsize=9, fontweight="bold")

            info = f"{lang_a}: {da['count']} repos     |     {lang_b}: {db['count']} repos"
            fig.text(0.5, 0.01, info, ha="center", fontsize=9, color="gray")
            fig.tight_layout(rect=[0, 0.04, 1, 0.95])
            _embed(fig)

        def show_top5_overview():
            _clear_canvas()
            top5 = [l[0] for l in data["sorted_langs"][:5] if l[0] in data["lang_details"]]
            if not top5:
                return

            colors = list(plt.cm.tab10.colors)
            fig, axes = plt.subplots(1, 3, figsize=(14, 5))
            fig.suptitle("RQ07 – Top 5 Linguagens: Visão Geral Comparativa",
                         fontsize=13, fontweight="bold")

            panels = [
                (axes[0], "Média de PRs", "PRs",
                 [data["lang_details"][l]["stats_prs"]["mean"] for l in top5], False),
                (axes[1], "Média de Releases", "Releases",
                 [data["lang_details"][l]["stats_releases"]["mean"] for l in top5], False),
                (axes[2], "Média de Issues Fechadas (%)", "% Issues Fechadas",
                 [data["lang_details"][l]["stats_issues"]["mean"] for l in top5], True),
            ]

            for ax, title, ylabel, vals, is_pct in panels:
                bars = ax.bar(top5, vals, color=colors[: len(top5)])
                ax.set_title(title, fontsize=11)
                ax.set_ylabel(ylabel, fontsize=9)
                ax.set_ylim(bottom=0)
                ax.spines["top"].set_visible(False)
                ax.spines["right"].set_visible(False)
                for bar, val in zip(bars, vals):
                    offset = max(bar.get_height() * 0.02, ax.get_ylim()[1] * 0.01)
                    ax.text(bar.get_x() + bar.get_width() / 2.0,
                            bar.get_height() + offset,
                            self._fmt_val(val, is_pct),
                            ha="center", va="bottom", fontsize=8, fontweight="bold")

            fig.tight_layout()
            _embed(fig)

        ttk.Button(ctrl_frame, text="🔍 Comparar", command=update_comparison).pack(
            side=tk.LEFT, padx=12
        )
        ttk.Button(ctrl_frame, text="📊 Top 5 Visão Geral", command=show_top5_overview).pack(
            side=tk.LEFT, padx=4
        )

        update_comparison()


def main():
    root = tk.Tk()
    app = GitHubAnalyzerGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
