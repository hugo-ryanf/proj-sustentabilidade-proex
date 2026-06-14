"""
Scraper de projetos de extensão SIGAA/UFPB — Sustentabilidade.
Mapeia projetos de extensão com foco no tema de sustentabilidade.

Dependências:
    pip install playwright pandas openpyxl python-dotenv
    playwright install chromium
"""

from playwright.sync_api import sync_playwright

from scraper.config import HEADLESS, SLOW_MO, DB_PATH, CENTROS
from scraper.database import init_db, centros_ja_concluidos, marcar_centro_concluido
from scraper.navigation import fazer_login, ir_para_busca, aplicar_filtros
from scraper.runner import processar_centro
from scraper.excel_export import exportar_excel


def main():
    conn      = init_db(DB_PATH)
    ja_feitos = centros_ja_concluidos(conn)

    pendentes = [(v, n) for v, n in CENTROS if n not in ja_feitos]
    if ja_feitos:
        print(f"Retomando: {len(ja_feitos)} centro(s) já concluído(s), {len(pendentes)} pendente(s).")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS, slow_mo=SLOW_MO, args=["--start-maximized"])
        context = browser.new_context(no_viewport=True)

        # Bloqueia apenas fontes e mídia; mantém CSS e imagens para visualização
        context.route("**/*", lambda route: route.abort()
            if route.request.resource_type in ("font", "media")
            else route.continue_()
        )

        page = context.new_page()
        fazer_login(page)

        for centro_valor, centro_nome in pendentes:
            print(f"\n{'='*60}")
            print(f"CENTRO: {centro_nome}")
            print(f"{'='*60}")

            aplicar_filtros(page, centro_valor, centro_nome)
            salvos = processar_centro(page, centro_nome, conn)
            print(f"  → {salvos} projeto(s) relevante(s) salvos.")

            marcar_centro_concluido(conn, centro_nome)
            ir_para_busca(page)

        browser.close()

    conn.close()
    exportar_excel(init_db(DB_PATH))


if __name__ == "__main__":
    main()
