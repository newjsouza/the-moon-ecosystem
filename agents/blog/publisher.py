"""
agents/blog/publisher.py
Blog Publisher Agent - Handles mkdocs, terminal installations and deployments.
"""
import asyncio
import os
import shutil
import frontmatter
import markdown
from jinja2 import Environment, FileSystemLoader
from core.agent_base import AgentBase, TaskResult, AgentPriority
from utils.logger import setup_logger

class BlogPublisherAgent(AgentBase):
    def __init__(self):
        super().__init__()
        self.priority = AgentPriority.CRITICAL
        self.description = "Blog Publisher - Premium Engine V2 via Python"
        self.logger = setup_logger("BlogPublisherAgent")
        self.bus = None  # MessageBus reference for events

    async def _execute(self, task: str, **kwargs) -> TaskResult:
        orchestrator = kwargs.get("orchestrator")
        markdown_content = kwargs.get("markdown")
        blog_dir = "meu_blog_autonomo"
        templates_dir = os.path.join(os.path.dirname(__file__), "templates")

        self.logger.info("Garantindo estrutura Vanilla do Blog V2...")
        os.makedirs(f"{blog_dir}/posts_md", exist_ok=True)
        os.makedirs(f"{blog_dir}/assets", exist_ok=True)

        self.logger.info("Copiando o CSS de base...")
        if os.path.exists(f"{templates_dir}/style.css"):
            shutil.copy(f"{templates_dir}/style.css", f"{blog_dir}/assets/style.css")

        self.logger.info("Salvando o raw markdown...")
        safe_title = task.replace(" ", "_").lower()
        md_filepath = f"{blog_dir}/posts_md/{safe_title}.md"
        with open(md_filepath, "w", encoding="utf-8") as f:
            f.write(markdown_content)

        self.logger.info("Iniciando Jinja2 Compilation (Static Site Generation)...")
        try:
            env = Environment(loader=FileSystemLoader(templates_dir))
            post_template = env.get_template("post.html")
            index_template = env.get_template("index.html")

            all_posts = []

            # Lê todos os markdowns disponíveis (funcionando como um bando de dados)
            for file in os.listdir(f"{blog_dir}/posts_md"):
                if file.endswith(".md"):
                    with open(f"{blog_dir}/posts_md/{file}", "r", encoding="utf-8") as f:
                        post = frontmatter.load(f)

                        # Converte corpo Markdown para HTML real
                        html_body = markdown.markdown(post.content)

                        # Metadados
                        slug = file.replace(".md", "")
                        post_data = {
                            "title": post.metadata.get("title", task),
                            "date": post.metadata.get("date", "Hoje"),
                            "author": post.metadata.get("author", "Sistema"),
                            "category": post.metadata.get("category", "Geral"),
                            "image": post.metadata.get("image", "capa.jpg"),
                            "excerpt": post.metadata.get("excerpt", "Saiba mais neste post."),
                            "content": html_body,
                            "slug": slug
                        }
                        all_posts.append(post_data)

                        # Renderiza e salva o HTML da postagem isolada
                        rendered_post = post_template.render(post=post_data)
                        with open(f"{blog_dir}/{slug}.html", "w", encoding="utf-8") as pf:
                            pf.write(rendered_post)

            # Renderiza e salva a Home (index.html)
            rendered_index = index_template.render(posts=all_posts)
            with open(f"{blog_dir}/index.html", "w", encoding="utf-8") as inf:
                inf.write(rendered_index)

        except Exception as e:
            self.logger.error(f"Erro durante compilação do blog: {e}")
            return TaskResult(success=False, error=str(e))

        # Hook assíncrono: exportar assets (PDF + diagramas) em background
        # Passa referência ao bus para publicação de evento após exports
        asyncio.create_task(
            self._export_post_assets_async(
                post_id=safe_title,
                content=markdown_content,
                html_path=f"{blog_dir}/{safe_title}.html",
                md_filepath=md_filepath,
            )
        )

        return TaskResult(success=True, data={"status": "Posted", "url": f"{blog_dir}/index.html"})

    async def _export_post_assets_async(
        self,
        post_id: str,
        content: str,
        html_path: str,
        md_filepath: str,
    ) -> None:
        """
        Hook assíncrono pós-publicação: gera PDF e diagramas do post.
        Executado em background — não bloqueia nem falha a publicação.
        Controlado por ENABLE_CLI_EXPORTS no .env.
        Publica evento 'blog.published' no MessageBus após exports.
        """
        from core.message_bus import MessageBus

        if os.environ.get("ENABLE_CLI_EXPORTS", "false").lower() != "true":
            return

        export_result = {
            "post_id": post_id,
            "html_path": html_path,
            "md_path": md_filepath,
            "pdf_path": None,
            "images": [],
            "has_pdf": False,
            "has_images": False,
        }

        try:
            from skills.cli_harnesses.blog_cli_exporter import BlogCLIExporter, extract_mermaid_blocks
            exporter = BlogCLIExporter()
            caps = exporter.capabilities()
            if not any(caps.values()):
                self.logger.info("BlogCLIExporter: nenhuma capability disponível")
                return

            # Extrair diagramas Mermaid do conteúdo
            diagrams = extract_mermaid_blocks(content)

            result = await exporter.generate_post_assets(
                post_id=post_id,
                content=content,
                diagrams=diagrams,
                formats=["pdf"],
            )

            # Atualizar resultado para evento
            export_result["pdf_path"] = result.get("pdf")
            export_result["has_pdf"] = bool(result.get("pdf"))

            diagram_paths = [d.get("path") for d in result.get("diagrams", []) if d.get("path")]
            export_result["images"] = diagram_paths
            export_result["has_images"] = len(diagram_paths) > 0

            self.logger.info(
                f"Blog export: post_id={post_id} "
                f"pdf={result.get('pdf')} "
                f"diagrams={len(result.get('diagrams', []))}"
            )

        except Exception as exc:
            # NUNCA propagar exceção — apenas logar
            self.logger.warning(f"_export_post_assets_async: erro não-crítico: {exc}")

        # Publicar evento no MessageBus (mesmo se exports falharam)
        try:
            # Obter MessageBus (singleton)
            bus = self.bus if self.bus else MessageBus()
            await bus.publish(
                sender="blog_publisher",
                topic="blog.published",
                payload=export_result,
            )
            self.logger.info(f"Evento blog.published publicado: {post_id}")
        except Exception as exc:
            self.logger.warning(f"Falha ao publicar evento blog.published: {exc}")
