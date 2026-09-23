# =========================
# FONTES DE DADOS
# =========================
# Aceita:
# 1) URL normal do Google Sheets (.../edit?...)
# 2) URL CSV publicada
#
# Para planilhas privadas, a leitura pública por CSV não funcionará.
# Nesse caso, publique somente as abas necessárias ou adapte a autenticação.

CHAMADOS_SHEET_URL = "https://docs.google.com/spreadsheets/d/1_iq62b-GC3BF13omMi3TKMA9pAwNsLNGK2l7-GyWxLY/edit"
CHAMADOS_GID = "1899782625"

META_PECAS_SHEET_URL = "https://docs.google.com/spreadsheets/d/1i9Dj25MFL8mFDCsNoVgfJYdRx_XRdKvJPdRpabxrJps/edit"
META_PECAS_GID = "0"

META_MO_SHEET_URL = "https://docs.google.com/spreadsheets/d/1yo87j1OHoV8Ve-YlwTrSLjJ_YwAekwQyNxbZ7_ALnS8/edit"
META_MO_GID = "0"

# Metas totais. Podem ser alteradas aqui sem mexer no restante do projeto.
META_PECAS_TOTAL = 710000.00
META_MO_TOTAL = 370000.00

# Duração do cache dos dados lidos do Google Sheets (em segundos).
# É isso que garante a atualização automática dos números.
CACHE_TTL_SECONDS = 600

# Quantos segundos cada TELA fica visível antes de trocar para a próxima.
# O dashboard revezada automaticamente entre as telas definidas em PAGES (app.py).
PAGE_ROTATION_SECONDS = 20

# Mapeamento opcional para eliminar ambiguidades de geocodificação.
# Exemplo: {"Não Me Toque": "Não-Me-Toque, RS, Brasil"}
CITY_QUERY_OVERRIDES = {}

# Se uma cidade puder existir nos dois estados e a base não trouxer UF,
# informe aqui a UF correta.
CITY_UF_OVERRIDES = {
    # "Lages": "SC",
    # "Passo Fundo": "RS",
}
