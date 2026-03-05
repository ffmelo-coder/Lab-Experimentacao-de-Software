import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime
import time
import threading
from github_utils import (
    calculate_age_in_days,
    calculate_days_since_push,
    calculate_closed_issues_ratio,
    format_age,
    fetch_repositories,
    validate_token,
    export_to_csv,
)


class GitHubAnalyzerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Análise de Repositórios Populares - GitHub")
        self.root.geometry("1200x700")
        self.root.resizable(False, False)

        self.token = tk.StringVar()
        self.token.trace("w", self.on_token_change)
        self.all_repos = []
        self.current_page = 0
        self.items_per_page = 20
        self.is_fetching = False
        self.stop_collection = False
        self.progress_value = 0
        self.page_input = tk.StringVar(value="0")

        self.setup_ui()

    def setup_ui(self):

        top_frame = ttk.Frame(self.root, padding="10")
        top_frame.pack(fill=tk.X)

        ttk.Label(top_frame, text="GitHub Token:", font=("Arial", 10, "bold")).pack(
            side=tk.LEFT, padx=5
        )
        token_entry = ttk.Entry(top_frame, textvariable=self.token, width=50, show="*")
        token_entry.pack(side=tk.LEFT, padx=5)

        self.btn_start = ttk.Button(
            top_frame,
            text="▶ Iniciar Coleta",
            command=self.start_collection,
            state=tk.DISABLED,
        )
        self.btn_start.pack(side=tk.LEFT, padx=10)

        self.btn_stop = ttk.Button(
            top_frame,
            text="⏹ Encerrar Processo",
            command=self.stop_collection_process,
            state=tk.DISABLED,
        )
        self.btn_stop.pack(side=tk.LEFT, padx=5)

        progress_frame = ttk.Frame(self.root, padding="10")
        progress_frame.pack(fill=tk.X)

        ttk.Label(progress_frame, text="Progresso:", font=("Arial", 9)).pack(
            side=tk.LEFT, padx=5
        )
        self.progress_bar = ttk.Progressbar(
            progress_frame, length=600, mode="determinate"
        )
        self.progress_bar.pack(side=tk.LEFT, padx=5)

        self.progress_label = ttk.Label(
            progress_frame, text="0%", font=("Arial", 9, "bold")
        )
        self.progress_label.pack(side=tk.LEFT, padx=5)

        self.btn_download = ttk.Button(
            progress_frame,
            text="💾 Baixar CSV",
            command=self.download_csv,
            state=tk.DISABLED,
        )
        self.btn_download.pack(side=tk.LEFT, padx=10)

        table_frame = ttk.Frame(self.root, padding="10")
        table_frame.pack(fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(table_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        columns = (
            "#",
            "Repositório",
            "Linguagem",
            "Idade",
            "PRs",
            "Releases",
            "Issues %",
            "Dias Atualiz.",
        )
        self.tree = ttk.Treeview(
            table_frame,
            columns=columns,
            show="headings",
            yscrollcommand=scrollbar.set,
            height=20,
        )
        scrollbar.config(command=self.tree.yview)

        self.tree.heading("#", text="#")
        self.tree.heading("Repositório", text="Repositório")
        self.tree.heading("Linguagem", text="Linguagem")
        self.tree.heading("Idade", text="Idade")
        self.tree.heading("PRs", text="PRs")
        self.tree.heading("Releases", text="Releases")
        self.tree.heading("Issues %", text="Issues %")
        self.tree.heading("Dias Atualiz.", text="Dias Atualiz.")

        self.tree.column("#", width=40, anchor=tk.CENTER)
        self.tree.column("Repositório", width=300, anchor=tk.W)
        self.tree.column("Linguagem", width=100, anchor=tk.CENTER)
        self.tree.column("Idade", width=100, anchor=tk.CENTER)
        self.tree.column("PRs", width=80, anchor=tk.CENTER)
        self.tree.column("Releases", width=80, anchor=tk.CENTER)
        self.tree.column("Issues %", width=90, anchor=tk.CENTER)
        self.tree.column("Dias Atualiz.", width=110, anchor=tk.CENTER)

        self.tree.pack(fill=tk.BOTH, expand=True)

        nav_frame = ttk.Frame(self.root, padding="10")
        nav_frame.pack(fill=tk.X)

        self.btn_prev = ttk.Button(
            nav_frame, text="◀ Anterior", command=self.prev_page, state=tk.DISABLED
        )
        self.btn_prev.pack(side=tk.LEFT, padx=5)

        ttk.Label(nav_frame, text="Página", font=("Arial", 9)).pack(
            side=tk.LEFT, padx=(20, 5)
        )

        self.page_entry = ttk.Entry(
            nav_frame,
            textvariable=self.page_input,
            width=5,
            justify=tk.CENTER,
            font=("Arial", 9),
        )
        self.page_entry.pack(side=tk.LEFT)
        self.page_entry.bind("<Return>", self.goto_page_from_entry)

        self.page_total_label = ttk.Label(
            nav_frame, text="de 0", font=("Arial", 9, "bold")
        )
        self.page_total_label.pack(side=tk.LEFT, padx=(5, 20))

        self.btn_next = ttk.Button(
            nav_frame, text="Próxima ▶", command=self.next_page, state=tk.DISABLED
        )
        self.btn_next.pack(side=tk.LEFT, padx=5)

        self.status_label = ttk.Label(
            nav_frame, text="Aguardando início...", font=("Arial", 9), foreground="blue"
        )
        self.status_label.pack(side=tk.RIGHT, padx=10)

    def on_token_change(self, *args):
        if len(self.token.get().strip()) > 0:
            self.btn_start.config(state=tk.NORMAL)
        else:
            self.btn_start.config(state=tk.DISABLED)

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

        self.is_fetching = True
        self.stop_collection = False
        self.all_repos = []
        self.current_page = 0
        self.btn_start.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        self.btn_download.config(state=tk.DISABLED)
        self.progress_bar["value"] = 0
        self.progress_label.config(text="0%")

        thread = threading.Thread(target=self.fetch_all_repositories, args=(token,))
        thread.daemon = True
        thread.start()

    def fetch_all_repositories(self, token):

        cursor = None
        page_size = 10
        total_fetched = 0
        max_repos = 1000

        self.update_status(f"Coletando {max_repos} repositórios...", "blue")

        while total_fetched < max_repos and not self.stop_collection:
            page_num = (total_fetched // page_size) + 1
            self.update_status(f"Buscando página {page_num}/100...", "blue")

            data = fetch_repositories(token, cursor, page_size)

            if not data or "data" not in data:
                error_msg = f"Erro ao buscar dados. Coletados: {len(self.all_repos)} repositórios"
                self.update_status(error_msg, "red")
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
                        f"Os dados já coletados estão disponíveis para visualização.",
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

            progress = (total_fetched / max_repos) * 100
            self.update_progress(progress)

            # atualizar display conforme dados chegam
            current_page_end = (self.current_page + 1) * self.items_per_page
            if (
                total_fetched <= self.items_per_page
                or total_fetched >= current_page_end
            ):
                self.root.after(0, self.display_current_page)

            page_info = search_data["pageInfo"]
            if (
                not page_info["hasNextPage"]
                or total_fetched >= max_repos
                or self.stop_collection
            ):
                break

            cursor = page_info["endCursor"]
            time.sleep(2)  # rate limiting

        self.is_fetching = False
        self.root.after(0, lambda: self.btn_stop.config(state=tk.DISABLED))

        if self.stop_collection:
            status_msg = (
                f"⏹ Processo encerrado: {len(self.all_repos)} repositórios coletados"
            )
            status_color = "orange"
        elif len(self.all_repos) >= max_repos:
            status_msg = f"✓ Coleta concluída! {len(self.all_repos)} repositórios"
            status_color = "green"
        elif len(self.all_repos) > 0:
            status_msg = (
                f"⚠️ Coleta parcial: {len(self.all_repos)} repositórios coletados"
            )
            status_color = "orange"
        else:
            status_msg = "❌ Nenhum repositório foi coletado"
            status_color = "red"

        self.update_status(status_msg, status_color)
        self.update_progress(
            100
            if len(self.all_repos) >= max_repos
            else (len(self.all_repos) / max_repos) * 100
        )

        if len(self.all_repos) > 0:
            self.root.after(0, self.enable_download)

        self.root.after(0, self.display_current_page)

    def update_progress(self, value):

        def update():
            self.progress_bar["value"] = value
            self.progress_label.config(text=f"{int(value)}%")

        self.root.after(0, update)

    def update_status(self, message, color):

        def update():
            self.status_label.config(text=message, foreground=color)

        self.root.after(0, update)

    def display_current_page(self):

        for item in self.tree.get_children():
            self.tree.delete(item)

        if not self.all_repos:
            self.page_input.set("0")
            self.page_total_label.config(text="de 0")
            self.btn_prev.config(state=tk.DISABLED)
            self.btn_next.config(state=tk.DISABLED)
            return

        start_idx = self.current_page * self.items_per_page
        end_idx = min(start_idx + self.items_per_page, len(self.all_repos))

        for i in range(start_idx, end_idx):
            repo = self.all_repos[i]
            node = repo["node"]

            name = f"{node['owner']['login']}/{node['name']}"
            language = (
                node["primaryLanguage"]["name"] if node["primaryLanguage"] else "N/A"
            )
            age = format_age(calculate_age_in_days(node["createdAt"]))
            prs = node["pullRequests"]["totalCount"]
            releases = node["releases"]["totalCount"]

            total_issues = node["issues"]["totalCount"]
            closed_issues = node["closedIssues"]["totalCount"]
            issues_ratio = calculate_closed_issues_ratio(closed_issues, total_issues)

            days_since = calculate_days_since_push(node["pushedAt"])

            if days_since == 0:
                days_display = "Hoje"
            elif days_since == 1:
                days_display = "1d"
            else:
                days_display = f"{days_since}d"

            self.tree.insert(
                "",
                tk.END,
                values=(
                    i + 1,
                    name,
                    language,
                    age,
                    prs,
                    releases,
                    f"{issues_ratio:.1f}%",
                    days_display,
                ),
            )

        total_pages = (
            len(self.all_repos) + self.items_per_page - 1
        ) // self.items_per_page
        self.page_input.set(str(self.current_page + 1))
        self.page_total_label.config(text=f"de {total_pages}")

        self.btn_prev.config(state=tk.NORMAL if self.current_page > 0 else tk.DISABLED)

        has_next = end_idx < len(self.all_repos)
        self.btn_next.config(state=tk.NORMAL if has_next else tk.DISABLED)

        print(
            f"DEBUG: Página {self.current_page + 1}/{total_pages}, Repos: {len(self.all_repos)}, Range: {start_idx}-{end_idx}, Has Next: {has_next}"
        )

        self.root.update_idletasks()

    def prev_page(self):

        print(
            f"DEBUG prev_page: current={self.current_page}, total_repos={len(self.all_repos)}"
        )
        if self.current_page > 0:
            self.current_page -= 1
            self.display_current_page()
        else:
            print("DEBUG: Já está na primeira página")

    def goto_page_from_entry(self, event=None):

        try:
            page_num = int(self.page_input.get())

            if not self.all_repos:
                self.page_input.set("0")
                messagebox.showwarning("Aviso", "Nenhum dado carregado ainda!")
                return

            total_pages = (
                len(self.all_repos) + self.items_per_page - 1
            ) // self.items_per_page

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
            messagebox.showwarning(
                "Entrada Inválida", "Por favor, digite um número válido."
            )

    def next_page(self):

        total_pages = (
            len(self.all_repos) + self.items_per_page - 1
        ) // self.items_per_page
        print(
            f"DEBUG next_page: current={self.current_page}, total_pages={total_pages}, total_repos={len(self.all_repos)}"
        )
        if self.current_page < total_pages - 1:
            self.current_page += 1
            self.display_current_page()
        else:
            print("DEBUG: Já está na última página")

    def enable_download(self):

        self.btn_download.config(state=tk.NORMAL)
        self.btn_start.config(state=tk.NORMAL)

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
                self.update_status(f"✓ CSV exportado com sucesso!", "green")
            else:
                messagebox.showerror("Erro", "Erro ao salvar arquivo")
                self.update_status("Erro ao exportar CSV", "red")

        except Exception as e:
            messagebox.showerror("Erro", f"Erro ao salvar arquivo:\n{str(e)}")


def main():
    root = tk.Tk()
    app = GitHubAnalyzerGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
