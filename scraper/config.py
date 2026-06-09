"""Configuração e constantes do scraper."""

import os
from dotenv import load_dotenv

load_dotenv()

USUARIO = os.getenv("SIGAA_USUARIO", "")
SENHA   = os.getenv("SIGAA_SENHA", "")

if not USUARIO or not SENHA:
    raise SystemExit("Erro: defina SIGAA_USUARIO e SIGAA_SENHA no arquivo .env")

HEADLESS     = False   # True para rodar sem janela (mais rápido)
SLOW_MO      = 0
XLSX_PATH    = "projetos_sustentabilidade.xlsx"
DB_PATH      = "progresso.db"
LIMITE_TESTE = None     # None para rodar todos

STATUS_EM_EXECUCAO = "103"
PALAVRAS_CHAVE     = ["sustentabilidade", "desenvolvimento sustentável", "meio ambiente"]
COLUNAS_EXCEL      = ["codigo", "titulo", "coordenador", "centro", "unidade", "area_tematica"]

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
