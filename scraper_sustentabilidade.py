"""
Scraper de projetos de extensão SIGAA/UFPB — Sustentabilidade.
Mapeia projetos de extensão com foco no tema de sustentabilidade.

Dependências:
    pip install playwright pandas openpyxl python-dotenv
    playwright install chromium
"""

import os
import re
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, Page, TimeoutError as PWTimeout

# ---------------------------------------------------------------------------
# CONFIGURAÇÃO
# ---------------------------------------------------------------------------

load_dotenv()
USUARIO = os.getenv("SIGAA_USUARIO", "")
SENHA   = os.getenv("SIGAA_SENHA", "")

if not USUARIO or not SENHA:
    raise SystemExit("Erro: defina SIGAA_USUARIO e SIGAA_SENHA no arquivo .env")

HEADLESS  = False
XLSX_PATH = "projetos_sustentabilidade.xlsx"

STATUS_EM_EXECUCAO = "103"

CENTROS = [
    ("1632", "CCAE"),
    ("1614", "CCM"),
    ("2564", "CCTA"),
    ("1383", "CE"),
    ("1852", "CEAR"),
    ("1860", "CENTRO DE BIOTECNOLOGIA"),
    ("1466", "CCA"),
    ("1357", "CCS"),
    ("1333", "CCEN"),
    ("1472", "CCHSA"),
    ("1345", "CCHLA"),
    ("1388", "CCJ"),
    ("1327", "CCSA"),
    ("1856", "CI"),
    ("3687", "ETS"),
    ("1374", "CT"),
    ("1580", "CTDR"),
    ("3746", "PARFOR"),
]

# ---------------------------------------------------------------------------
# LOGIN E NAVEGAÇÃO INICIAL
# ---------------------------------------------------------------------------

def fazer_login(page: Page):
    print("Navegando para o SIGAA...")
    page.goto("https://sigaa.ufpb.br/sigaa/logon.jsf")
    page.wait_for_selector("#form\\:login")

    page.fill("#form\\:login", USUARIO)
    page.fill("#form\\:senha", SENHA)
    page.click("#form\\:entrar")
    page.wait_for_load_state("networkidle")

    # Seleciona o papel de Servidor (pode aparecer tela de seleção de vínculo)
    try:
        page.locator("//strong[contains(., 'Servidor')]").first.click()
        page.wait_for_load_state("networkidle")
    except Exception:
        pass

    # Navega para Módulos
    page.locator("a[href='/sigaa/menu/']").click()
    page.wait_for_load_state("networkidle")

    # Clica no módulo de Extensão
    page.locator("div").filter(has_text=re.compile(r"^Extensão$")).click()
    page.wait_for_load_state("networkidle")

    # Clica em Buscar Ações
    page.locator("#menuExtensao\\:buscarAcoes").click()
    page.wait_for_load_state("networkidle")

    print("Login realizado com sucesso.")


# ---------------------------------------------------------------------------
# FILTROS
# ---------------------------------------------------------------------------

def aplicar_filtros(page: Page, centro_valor: str, centro_nome: str):
    print(f"  Aplicando filtros para: {centro_nome}")

    # Seleciona o centro
    page.select_option("#formBuscaAtividade\\:buscaCentro", value=centro_valor)

    # Seleciona situação "EM EXECUÇÃO"
    page.locator("#formBuscaAtividade\\:buscaSituacao").evaluate(
        """(el, valor) => {
            for (const opt of el.options) {
                opt.selected = opt.value === valor;
            }
        }""",
        STATUS_EM_EXECUCAO,
    )

    # Marca o checkbox para ativar o filtro de situação
    cb = page.locator("#formBuscaAtividade\\:selectBuscaSituacaoAtividade")
    if not cb.is_checked():
        cb.check()

    # Clica em Buscar
    page.locator("#formBuscaAtividade\\:btBuscar").click()
    page.wait_for_load_state("networkidle")

    print(f"  Filtros aplicados.")


# ---------------------------------------------------------------------------
# SCRIPT PRINCIPAL
# ---------------------------------------------------------------------------

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS, slow_mo=150, args=["--start-maximized"])
        context = browser.new_context(no_viewport=True)
        page    = context.new_page()

        fazer_login(page)

        for centro_valor, centro_nome in CENTROS:
            print(f"\n{'='*60}")
            print(f"CENTRO: {centro_nome} (valor={centro_valor})")
            print(f"{'='*60}")

            aplicar_filtros(page, centro_valor, centro_nome)

            # Verifica se há resultados
            try:
                page.wait_for_selector("a[title='Visualizar Ação']", timeout=8_000)
                total = page.locator("a[title='Visualizar Ação']").count()
                print(f"  {total} projeto(s) encontrado(s).")
            except PWTimeout:
                print("  Sem resultados para este centro.")

            # Volta ao formulário para o próximo centro
            page.locator("#menuExtensao\\:buscarAcoes").click()
            page.wait_for_load_state("networkidle")

        print("\nTodos os centros processados.")
        input("Pressione Enter para fechar o navegador...")

        browser.close()


if __name__ == "__main__":
    main()
