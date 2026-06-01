"""
Scraper de projetos de extensão SIGAA/UFPB — versão Playwright.
Coleta local de realização (tabela), resumo e justificativa.
Extrai municípios via fuzzy matching contra gabarito IBGE.

Dependências:
    pip install playwright pandas openpyxl rapidfuzz requests unidecode
    playwright install chromium
"""

import re
import time
import sqlite3
import requests
import pandas as pd
from unidecode import unidecode
from rapidfuzz import process, fuzz
from playwright.sync_api import sync_playwright, Page, TimeoutError as PWTimeout

# ---------------------------------------------------------------------------
# CONFIGURAÇÃO
# ---------------------------------------------------------------------------

from dotenv import load_dotenv
import os

load_dotenv()
USUARIO = os.getenv("SIGAA_USUARIO", "")
SENHA   = os.getenv("SIGAA_SENHA", "")

if not USUARIO or not SENHA:
    raise SystemExit("Erro: defina SIGAA_USUARIO e SIGAA_SENHA no arquivo .env")

STATUS_ALVO_VALORES = ["117", "103", "105"]  # PENDENTE DE RELATÓRIO, EM EXECUÇÃO, CONCLUÍDA
#EDITAIS_ALVO        = ["87","86","92","93","94","91","90","89","88","84","83","82","85","80","81","79","78","70"]
EDITAIS_ALVO        = ["87"]
DATA_INICIO_EXECUCAO = "01/01/2025"
DATA_FIM_EXECUCAO    = "31/12/2025"

HEADLESS  = False   # True para produção
DB_PATH   = "sigaa_projetos.db"
XLSX_PATH = "Levantamento_Editais_2025_Playwright.xlsx"

SCORE_MINIMO = 85   # Sensibilidade do fuzzy matching (0-100)

# ---------------------------------------------------------------------------
# GABARITO IBGE — municípios e microrregiões da PB
# ---------------------------------------------------------------------------

def normalizar(texto: str) -> str:
    texto = unidecode(texto).lower().strip()
    texto = re.sub(r"[^a-z0-9\s]", "", texto)
    texto = re.sub(r"\s+", " ", texto)
    return texto


def carregar_gabarito_ibge() -> tuple[dict, dict]:
    print("Carregando municípios da PB via IBGE...")
    url  = "https://servicodados.ibge.gov.br/api/v1/localidades/estados/PB/municipios"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()

    municipios: dict[str, dict] = {}
    for m in resp.json():
        chave = normalizar(m["nome"])
        municipios[chave] = {
            "nome":         m["nome"],
            "codigo_ibge":  str(m["id"]),
            "microrregiao": m["microrregiao"]["nome"],
            "mesorregiao":  m["microrregiao"]["mesorregiao"]["nome"],
        }

    microrregioes: dict[str, list[str]] = {}
    for info in municipios.values():
        chave = normalizar(info["microrregiao"])
        microrregioes.setdefault(chave, []).append(info["nome"])

    print(f"  {len(municipios)} municípios | {len(microrregioes)} microrregiões carregados.")
    return municipios, microrregioes


# ---------------------------------------------------------------------------
# EXTRATOR DE MUNICÍPIOS (fuzzy matching em texto livre)
# ---------------------------------------------------------------------------

def extrair_municipios_do_texto(
    texto: str,
    municipios: dict,
    microrregioes: dict,
) -> list[dict]:
    """Retorna lista de municípios encontrados no texto."""
    if not texto or not texto.strip():
        return []

    texto_norm = normalizar(texto)
    tokens     = texto_norm.split()
    encontrados: dict[str, dict] = {}

    nomes_municipios = list(municipios.keys())
    nomes_micro      = list(microrregioes.keys())

    for tamanho in range(1, 5):
        for i in range(len(tokens) - tamanho + 1):
            ngrama = " ".join(tokens[i: i + tamanho])
            if len(ngrama) < 3:
                continue

            # Testa município
            res = process.extractOne(ngrama, nomes_municipios, scorer=fuzz.token_sort_ratio, score_cutoff=SCORE_MINIMO)
            if res:
                chave, score, _ = res
                info = municipios[chave]
                cod  = info["codigo_ibge"]
                if cod not in encontrados:
                    pos    = texto_norm.find(ngrama)
                    trecho = texto[max(0, pos - 30): pos + len(ngrama) + 30].strip() if pos >= 0 else ""
                    encontrados[cod] = {**info, "score": score, "trecho": trecho}

            # Testa microrregião → expande para todos os municípios dela
            if len(ngrama) >= 4:
                res_m = process.extractOne(ngrama, nomes_micro, scorer=fuzz.token_sort_ratio, score_cutoff=SCORE_MINIMO)
                if res_m:
                    chave_m, score_m, _ = res_m
                    for nome_mun in microrregioes[chave_m]:
                        info_m = municipios.get(normalizar(nome_mun))
                        if info_m and info_m["codigo_ibge"] not in encontrados:
                            encontrados[info_m["codigo_ibge"]] = {
                                **info_m,
                                "score":  score_m,
                                "trecho": f"[via microrregião: {chave_m}]",
                            }

    return list(encontrados.values())


def resolver_municipios(projeto: dict, municipios: dict, microrregioes: dict) -> tuple[str, str, str, str]:
    """
    Estratégia de resolução:
      1. Usa municípios da tabela de locais (já estruturados pelo SIGAA)
      2. Se vazio ou 'Nenhum local listado', tenta resumo
      3. Se ainda vazio, tenta justificativa
      4. Se nenhum achou nada, devolve o local_de_realizacao bruto como fallback

    Retorna (municipios_str, fonte_utilizada, municipios_detalhados_json, score_medio)
    """
    municipios_tabela = projeto.get("municipios_tabela", "")
    resumo            = projeto.get("resumo", "")
    justificativa     = projeto.get("justificativa", "")
    local_bruto       = projeto.get("locais_realizacao", "")

# --- Passo 1 e 2: tenta extrair de resumo, depois justificativa ---
    for fonte, texto in [("resumo", resumo), ("justificativa", justificativa)]:
        preview = texto[:80].replace('\n', ' ') if texto else "(vazio)"
        print(f"    [debug] tentando {fonte}: '{preview}...'")
        encontrados = extrair_municipios_do_texto(texto, municipios, microrregioes)
        print(f"    [debug] {fonte} → {len(encontrados)} município(s) encontrado(s): {[m['nome'] for m in encontrados]}")
        if encontrados:
            nomes  = " | ".join(m["nome"] for m in encontrados)
            score  = round(sum(m["score"] for m in encontrados) / len(encontrados), 1)
            detalhe = "; ".join(
                f'{m["nome"]} ({m["microrregiao"]}) score={m["score"]} via={m["trecho"][:40]}'
                for m in encontrados
            )
            return nomes, fonte, detalhe, str(score)

    # --- Passo 3: fallback para a tabela de locais ---
    tabela_valida = (
        municipios_tabela
        and municipios_tabela not in ("Nenhum local listado", "Tabela ausente", "Erro na coleta", "")
    )
    print(f"    [debug] resumo/justificativa sem resultado — tabela: '{municipios_tabela[:60]}' | valida={tabela_valida}")
    if tabela_valida:
        return municipios_tabela, "tabela_locais_fallback", "", ""

    # --- Passo 4: fallback final ---
    print(f"    [debug] nenhuma fonte encontrou município — usando local bruto: '{local_bruto[:60]}'")
    fallback = local_bruto if local_bruto and local_bruto not in ("Nenhum local listado", "") else "Não identificado"
    return fallback, "fallback_local_bruto", "", ""


# ---------------------------------------------------------------------------
# BANCO DE DADOS LOCAL
# ---------------------------------------------------------------------------

def init_db(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS projetos (
            chave_unica         TEXT PRIMARY KEY,
            edital              TEXT,
            projeto             TEXT,
            coordenador         TEXT,
            status              TEXT,
            estados             TEXT,
            municipios_tabela   TEXT,
            bairros             TEXT,
            locais_realizacao   TEXT,
            resumo              TEXT,
            justificativa       TEXT,
            scraped_at          TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    return conn


def salvar(conn: sqlite3.Connection, d: dict):
    conn.execute("""
        INSERT OR REPLACE INTO projetos
          (chave_unica, edital, projeto, coordenador, status,
           estados, municipios_tabela, bairros, locais_realizacao,
           resumo, justificativa)
        VALUES
          (:chave_unica, :edital, :projeto, :coordenador, :status,
           :estados, :municipios_tabela, :bairros, :locais_realizacao,
           :resumo, :justificativa)
    """, d)
    conn.commit()


def ja_coletados(conn: sqlite3.Connection) -> set:
    return {r[0] for r in conn.execute("SELECT chave_unica FROM projetos").fetchall()}


# ---------------------------------------------------------------------------
# HELPERS DE NAVEGAÇÃO
# ---------------------------------------------------------------------------

def navegar_para_busca(page: Page):
    """Volta ao formulário de busca de ações de extensão."""
    page.get_by_text("Módulos").click()
    page.locator("//div[text()='Extensão']").click()
    page.locator("#menuExtensao\\:buscarAcoes").click()
    page.wait_for_load_state("networkidle")


def aplicar_filtros(page: Page, edital_valor: str):
    """Preenche todos os filtros do formulário de busca."""

    # Edital
    page.select_option("#formBuscaAtividade\\:buscaEdital", value=edital_valor)

    # Desmarca filtro de ano se estiver marcado
    cb_ano = page.locator("#formBuscaAtividade\\:selectBuscaAno")
    if cb_ano.is_checked():
        cb_ano.uncheck()

    # Período de execução
    page.fill("#formBuscaAtividade\\:dataInicio", DATA_INICIO_EXECUCAO)
    page.fill("#formBuscaAtividade\\:dataFim",    DATA_FIM_EXECUCAO)

    cb_periodo = page.locator("#formBuscaAtividade\\:selectBuscaPeriodo")
    if cb_periodo.count() and not cb_periodo.is_checked():
        cb_periodo.check()

    # Situação (select múltiplo)
    page.locator("#formBuscaAtividade\\:buscaSituacao").evaluate(
        """(el, valores) => {
            for (const opt of el.options) {
                opt.selected = valores.includes(opt.value);
            }
        }""",
        STATUS_ALVO_VALORES,
    )
    cb_sit = page.locator("#formBuscaAtividade\\:selectBuscaSituacaoAtividade")
    if cb_sit.count() and not cb_sit.is_checked():
        cb_sit.check()

    # Buscar
    page.locator("#formBuscaAtividade\\:btBuscar").click()
    page.wait_for_load_state("networkidle")


# ---------------------------------------------------------------------------
# COLETA DE DETALHES DE UM PROJETO
# ---------------------------------------------------------------------------

def coletar_detalhes(page: Page, nome_projeto: str, edital_nome: str, status: str) -> dict:
    """Extrai todos os campos da página de detalhe do projeto atual."""
    dados = {
        "edital":             edital_nome,
        "projeto":            nome_projeto,
        "status":             status,
        "coordenador":        "",
        "estados":            "",
        "municipios_tabela":  "",
        "bairros":            "",
        "locais_realizacao":  "",
        "resumo":             "",
        "justificativa":      "",
    }

    # Coordenador
    try:
        dados["coordenador"] = page.locator(
            "//th[contains(text(),'Coordenação')]/following-sibling::td"
        ).first.inner_text().strip()
    except Exception:
        pass

    # Tabela de locais de realização
    try:
        page.wait_for_selector("#tbLocaisRealizacao tbody tr", timeout=5_000)
        linhas = page.locator("#tbLocaisRealizacao tbody tr").all()

        estados, municipios_t, bairros, espacos = [], [], [], []
        for linha in linhas:
            cols = linha.locator("td").all()
            if len(cols) >= 4 and cols[3].inner_text().strip():
                estados.append(cols[0].inner_text().strip() or "Não informado")
                municipios_t.append(cols[1].inner_text().strip() or "Não informado")
                bairros.append(cols[2].inner_text().strip() or "Não informado")
                espacos.append(cols[3].inner_text().strip())

        if espacos:
            dados["estados"]            = " | ".join(estados)
            dados["municipios_tabela"]  = " | ".join(municipios_t)
            dados["bairros"]            = " | ".join(bairros)
            dados["locais_realizacao"]  = " | ".join(espacos)
        else:
            dados["municipios_tabela"] = "Nenhum local listado"

    except PWTimeout:
        dados["municipios_tabela"] = "Tabela ausente"

    # Resumo
    try:
        dados["resumo"] = page.locator(
            "//td[b[contains(text(),'Resumo')]]"
        ).first.inner_text().replace("Resumo:", "").strip()
    except Exception:
        dados["resumo"] = ""
    print(f"    [debug] resumo coletado: '{dados['resumo'][:80]}'")

    # Justificativa
    try:
        dados["justificativa"] = page.locator(
            "//td[b[contains(text(),'Justificativa')]]"
        ).first.inner_text().replace("Justificativa:", "").strip()
    except Exception:
        dados["justificativa"] = ""
    print(f"    [debug] justificativa coletada: '{dados['justificativa'][:80]}'")

    dados["chave_unica"] = f"{edital_nome}|{nome_projeto}"
    return dados
# ---------------------------------------------------------------------------
# SCRIPT PRINCIPAL
# ---------------------------------------------------------------------------

def main():
    municipios, microrregioes = carregar_gabarito_ibge()
    conn   = init_db(DB_PATH)
    ja_vis = ja_coletados(conn)

    projetos_coletados: list[dict] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS, slow_mo=150)
        context = browser.new_context()
        page    = context.new_page()

        # --- Login ---
        print("Fazendo login...")
        page.goto("https://sigaa.ufpb.br/sigaa/logon.jsf")
        page.wait_for_selector("#form\\:login")
        page.fill("#form\\:login", USUARIO)
        page.fill("#form\\:senha", SENHA)
        page.click("#form\\:entrar")
        page.wait_for_load_state("networkidle")

        page.locator("//strong[contains(., 'Servidor')]").click()
        page.wait_for_load_state("networkidle")
        print("Login OK.")

        # --- Pré-coleta dos editais disponíveis ---
        navegar_para_busca(page)
        page.wait_for_selector("#formBuscaAtividade\\:buscaEdital")
        opcoes_editais = page.locator("#formBuscaAtividade\\:buscaEdital option").all()
        editais_disponiveis = [
            (opt.get_attribute("value"), opt.inner_text().strip())
            for opt in opcoes_editais[1:]   # pula o "Selecione"
            if opt.get_attribute("value") in EDITAIS_ALVO
        ]
        print(f"{len(editais_disponiveis)} editais alvo encontrados.")

        # --- Loop por edital ---
        for edital_valor, edital_nome in editais_disponiveis:
            print(f"\n{'='*60}")
            print(f"EDITAL: {edital_nome} (valor={edital_valor})")
            print(f"{'='*60}")

            navegar_para_busca(page)
            aplicar_filtros(page, edital_valor)

            # Verifica se há resultados
            try:
                page.wait_for_selector("a[title='Visualizar Ação']", timeout=10_000)
            except PWTimeout:
                print("  Sem resultados para este edital. Pulando.")
                continue

            total = page.locator("a[title='Visualizar Ação']").count()
            print(f"  {total} projeto(s) encontrado(s).")

            # Coleta nomes e status antes de entrar nos detalhes
            nomes_xpath  = "//td[i[contains(text(), 'Coordenador')]]"
            status_xpath = "//td[i[contains(text(), 'Coordenador')]]/following-sibling::td[2]"

            for i in range(total):
                # Re-localiza elementos (DOM pode ter mudado após voltar)
                page.wait_for_selector("#formBuscaAtividade\\:btBuscar")

                icones  = page.locator("a[title='Visualizar Ação']").all()
                nomes   = page.locator(nomes_xpath).all()
                status_els = page.locator(status_xpath).all()

                if i >= len(icones):
                    print(f"  Alinhamento perdido no item {i}. Encerrando edital.")
                    break

                nome_projeto = nomes[i].inner_text().split("\n")[0].strip() if i < len(nomes) else "Desconhecido"
                status       = " ".join(status_els[i].inner_text().strip().split()).lower() if i < len(status_els) else ""
                chave        = f"{edital_nome}|{nome_projeto}"

                print(f"  [{i+1}/{total}] {nome_projeto}")

                if chave in ja_vis:
                    print("    → já coletado, pulando.")
                    continue

                # Entra na página de detalhe
                icones[i].click()
                page.wait_for_load_state("networkidle")

                dados = coletar_detalhes(page, nome_projeto, edital_nome, status)

                if dados is None:
                    print(f"    [debug] coletar_detalhes retornou None — pulando projeto.")
                    page.go_back()
                    page.wait_for_load_state("networkidle")
                    continue

                # Resolve municípios com fallback
                muns, fonte, detalhe, score = resolver_municipios(dados, municipios, microrregioes)
                dados["municipios_resolvidos"] = muns
                dados["fonte_municipio"]       = fonte
                dados["detalhe_extracao"]      = detalhe
                dados["score_medio"]           = score

                salvar(conn, dados)
                ja_vis.add(chave)
                projetos_coletados.append(dados)

                print(f"    Municípios ({fonte}): {muns[:80]}{'...' if len(muns) > 80 else ''}")

                # Volta para a lista
                page.go_back()
                page.wait_for_load_state("networkidle")
                page.wait_for_selector("#formBuscaAtividade\\:btBuscar")

        browser.close()

    # --- Exporta Excel final ---
    if projetos_coletados:
        df = pd.DataFrame(projetos_coletados)

        colunas = [
            "edital", "projeto", "coordenador", "status",
            "municipios_resolvidos", "fonte_municipio", "score_medio",
            "estados", "municipios_tabela", "bairros", "locais_realizacao",
            "detalhe_extracao",
        ]
        colunas_finais = [c for c in colunas if c in df.columns]
        df[colunas_finais].to_excel(XLSX_PATH, index=False, engine="openpyxl")
        print(f"\n{len(projetos_coletados)} projetos salvos em '{XLSX_PATH}'.")
    else:
        print("\nNenhum projeto coletado.")

    conn.close()


if __name__ == "__main__":
    main()