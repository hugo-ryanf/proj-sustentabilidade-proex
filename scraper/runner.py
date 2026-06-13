"""Loop principal de coleta: percorre os projetos de um centro e salva os relevantes."""

import sqlite3

from playwright.sync_api import Page, TimeoutError as PWTimeout

from scraper.config import LIMITE_TESTE, COLUNAS_EXCEL
from scraper.database import salvar_projeto, marcar_visitado, ja_visitados
from scraper.extractor import coletar_projeto, contem_palavra_chave


def processar_centro(page: Page, centro_nome: str, conn: sqlite3.Connection) -> int:
    try:
        page.wait_for_selector("a[title='Visualizar Ação']", timeout=8_000)
    except PWTimeout:
        print("  Sem resultados para este centro.")
        return 0

    total  = page.locator("a[title='Visualizar Ação']").count()
    limite = min(total, LIMITE_TESTE) if LIMITE_TESTE else total
    visitados = ja_visitados(conn)

    # Descobre quantos já foram visitados neste centro para exibir progresso correto
    ja_feitos_centro = sum(1 for i in range(limite) if f"{centro_nome}|{i}" in visitados)
    print(f"  {total} projeto(s) encontrado(s). Limite: {limite} | Já processados: {ja_feitos_centro}")

    salvos = 0

    for i in range(limite):
        chave = f"{centro_nome}|{i}"
        if chave in visitados:
            print(f"  [{i+1}/{limite}] Pulando (já processado).")
            continue

        botoes = page.locator("a[title='Visualizar Ação']").all()
        if i >= len(botoes):
            print(f"  Alinhamento perdido no item {i}. Encerrando centro.")
            break

        print(f"  [{i+1}/{limite}] Verificando...", end=" ", flush=True)

        botoes[i].click()
        page.wait_for_selector("//th[contains(.,'Título')]")

        dados = coletar_projeto(page)
        dados["centro"] = centro_nome

        campos_busca = f"{dados['titulo']} {dados['resumo']} {dados['justificativa']}"
        if contem_palavra_chave(campos_busca):
            print(f"\n    [SELECIONADO] {dados['titulo']}")
            salvar_projeto(conn, {k: dados[k] for k in COLUNAS_EXCEL})
            salvos += 1
        else:
            print(f"\n    [IGNORADO]    {dados['titulo']}")

        marcar_visitado(conn, chave)

        page.go_back()
        page.wait_for_selector("a[title='Visualizar Ação']")

    return salvos
