"""Extração de dados da página de detalhe do projeto e busca por palavras-chave."""

from playwright.sync_api import Page

from scraper.config import PALAVRAS_CHAVE


def contem_palavra_chave(texto: str) -> bool:
    texto_lower = texto.lower()
    return any(p in texto_lower for p in PALAVRAS_CHAVE)


def coletar_projeto(page: Page) -> dict:
    # Um único roundtrip ao browser extrai todos os campos de uma vez
    resultado = page.evaluate("""() => {
        const txt = el => el ? el.innerText.trim() : "";

        const thTitulo = [...document.querySelectorAll("th")].find(th => th.innerText.includes("Título"));
        const titulo = thTitulo ? txt(thTitulo.nextElementSibling) : "";

        const thCodigo = [...document.querySelectorAll("th")].find(th => th.innerText.includes("Código"));
        const codigo = thCodigo ? txt(thCodigo.nextElementSibling) : "";

        const thArea = [...document.querySelectorAll("th")].find(
            th => th.innerText.includes("Área Principal")
        );
        const area_tematica = thArea ? txt(thArea.nextElementSibling) : "";

        const coordFont = [...document.querySelectorAll("font")].find(f => f.innerText.includes("COORDENADOR"));
        let coordenador = "", unidade = "";
        if (coordFont) {
            const cells = coordFont.closest("tr").querySelectorAll("td");
            coordenador = cells[0] ? txt(cells[0]) : "";
            unidade     = cells[3] ? txt(cells[3]) : "";
        }

        const resumoStrong = [...document.querySelectorAll("strong")].find(s => s.innerText.includes("Resumo:"));
        let resumo = "";
        if (resumoStrong) {
            const nextP = resumoStrong.closest("p")?.nextElementSibling;
            resumo = nextP ? txt(nextP) : "";
        }

        const justTd = [...document.querySelectorAll("td")].find(td => {
            const b = td.querySelector("b");
            return b && b.innerText.includes("Justificativa:");
        });
        const justificativa = justTd ? txt(justTd).replace("Justificativa:", "").trim() : "";

        return { codigo, titulo, coordenador, unidade, area_tematica, resumo, justificativa };
    }""")

    return resultado
