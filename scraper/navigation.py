"""Login e navegação pelo menu do SIGAA."""

import re

from playwright.sync_api import Page

from scraper.config import USUARIO, SENHA, STATUS_EM_EXECUCAO


def fazer_login(page: Page):
    print("Navegando para o SIGAA...")
    page.goto("https://sigaa.ufpb.br/sigaa/logon.jsf", wait_until="domcontentloaded")
    page.wait_for_selector("#form\\:login")

    page.fill("#form\\:login", USUARIO)
    page.fill("#form\\:senha", SENHA)
    page.click("#form\\:entrar")
    page.wait_for_load_state("domcontentloaded")

    try:
        page.locator("//strong[contains(., 'Servidor')]").first.click()
        page.wait_for_load_state("domcontentloaded")
    except Exception:
        pass

    ir_para_busca(page)
    print("Login realizado com sucesso.")


def ir_para_busca(page: Page):
    """Navega pelo menu até o formulário de busca de ações, de qualquer página."""
    page.locator("a[href='/sigaa/menu/']").click()
    page.wait_for_load_state("domcontentloaded")
    page.locator("div").filter(has_text=re.compile(r"^Extensão$")).click()
    page.wait_for_load_state("domcontentloaded")
    page.locator("#menuExtensao\\:buscarAcoes").click()
    page.wait_for_selector("#formBuscaAtividade\\:buscaCentro")


def aplicar_filtros(page: Page, centro_valor: str, centro_nome: str):
    page.select_option("#formBuscaAtividade\\:buscaCentro", value=centro_valor)

    page.locator("#formBuscaAtividade\\:buscaSituacao").evaluate(
        """(el, valor) => {
            for (const opt of el.options) {
                opt.selected = opt.value === valor;
            }
        }""",
        STATUS_EM_EXECUCAO,
    )

    cb = page.locator("#formBuscaAtividade\\:selectBuscaSituacaoAtividade")
    if not cb.is_checked():
        cb.check()

    page.locator("#formBuscaAtividade\\:btBuscar").click()
    page.wait_for_load_state("domcontentloaded")
