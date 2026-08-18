import streamlit as st
import io, os, re, unicodedata, requests, csv
from datetime import datetime, timezone, timedelta
from PIL import Image as PILImage
from ddgs import DDGS

# ReportLab - Gerador Vetorial Profissional de PDF
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

# -----------------------------------------------------------------------------
# 🛠️ FUNÇÕES DE GESTÃO DE VENCIMENTOS E BASE LOCAL
# -----------------------------------------------------------------------------
ARQUIVO_VENCIMENTOS = "vencimentos.csv"

def registrar_vencimento(nome, cpf, email_operador, status_pep, data_emissao_dt, data_vencimento_str):
    """
    Grava ou ATUALIZA o histórico do relatório gerado.
    Evita duplicidade substituindo o registro caso o CPF já exista no arquivo.
    """
    cpf_limpo_key = re.sub(r'\D', '', cpf)
    registros_existentes = carregar_vencimentos()
    
    try:
        dt_venc = datetime.strptime(data_vencimento_str, "%d/%m/%Y").strftime("%Y-%m-%d")
    except Exception:
        dt_venc = data_vencimento_str

    novo_registro = {
        "Nome": nome.upper().strip(),
        "CPF": cpf.strip(),
        "CPF_Key": cpf_limpo_key,
        "Operador": email_operador,
        "Data_Emissao": data_emissao_dt.strftime("%d/%m/%Y %H:%M"),
        "Status_PEP": status_pep,
        "Data_Vencimento": data_vencimento_str,
        "Data_Vencimento_ISO": dt_venc
    }

    # Atualiza o registro existente ou adiciona um novo
    atualizado = False
    novos_registros = []
    for reg in registros_existentes:
        reg_cpf_key = re.sub(r'\D', '', reg.get("CPF", ""))
        if reg_cpf_key == cpf_limpo_key and cpf_limpo_key != "":
            novos_registros.append(novo_registro)
            atualizado = True
        else:
            novos_registros.append(reg)

    if not atualizado:
        novos_registros.append(novo_registro)

    try:
        campos = ["Nome", "CPF", "CPF_Key", "Operador", "Data_Emissao", "Status_PEP", "Data_Vencimento", "Data_Vencimento_ISO"]
        with open(ARQUIVO_VENCIMENTOS, mode='w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=campos, delimiter=';')
            writer.writeheader()
            for r in novos_registros:
                # Garante que as chaves estejam presentes
                r_line = {k: r.get(k, "") for k in campos}
                writer.writerow(r_line)
    except Exception as e:
        st.error(f"Erro ao salvar registro de vencimento: {e}")

def carregar_vencimentos():
    """Lê o arquivo local de vencimentos e retorna a lista de registros."""
    if not os.path.exists(ARQUIVO_VENCIMENTOS):
        return []
    
    registros = []
    try:
        with open(ARQUIVO_VENCIMENTOS, mode='r', encoding='utf-8-sig') as f:
            primeira_linha = f.readline()
            sep = ';' if ';' in primeira_linha else (',' if ',' in primeira_linha else '\t')
            f.seek(0)
            reader = csv.DictReader(f, delimiter=sep)
            for row in reader:
                registros.append(row)
    except Exception:
        pass
    return registros

def normalizar_texto(txt):
    """Remove acentos, caracteres especiais e converte para caixa baixa e espaços simples."""
    if not txt:
        return ""
    nfkd = unicodedata.normalize('NFD', str(txt))
    sem_acento = "".join([c for c in nfkd if not unicodedata.combining(c)])
    limpo = re.sub(r'[^a-zA-Z0-9\s]', ' ', sem_acento).lower()
    return " ".join(limpo.split())

def validar_cpf(cpf: str) -> bool:
    """Valida o cálculo dos dígitos verificadores do CPF (Módulo 11)."""
    cpf_limpo = re.sub(r'\D', '', str(cpf))
    
    if len(cpf_limpo) != 11 or cpf_limpo == cpf_limpo[0] * 11:
        return False
    
    soma = sum(int(cpf_limpo[i]) * (10 - i) for i in range(9))
    resto = (soma * 10) % 11
    digito_1 = 0 if resto == 10 else resto
    if digito_1 != int(cpf_limpo[9]):
        return False
        
    soma = sum(int(cpf_limpo[i]) * (11 - i) for i in range(10))
    resto = (soma * 10) % 11
    digito_2 = 0 if resto == 10 else resto
    if digito_2 != int(cpf_limpo[10]):
        return False
        
    return True

def identificar_arquivo_pep():
    """Localiza o arquivo da planilha de PEPs no diretório."""
    for arq in ["pep_oficial.csv", "pep_oficial.txt", "pep_oficial.csv.csv", "PEP_OFICIAL.csv", "PEP_OFICIAL.txt"]:
        if os.path.exists(arq):
            return arq
    try:
        for arq in os.listdir("."):
            nome_baixo = arq.lower()
            if "pep" in nome_baixo and (nome_baixo.endswith(".csv") or nome_baixo.endswith(".txt")):
                return arq
    except Exception:
        pass
    return None

def buscar_na_planilha_pep(nome_input, cpf_input):
    """Busca na planilha oficial da CGU com regra adaptativa anti-mascaramento."""
    caminho_final = identificar_arquivo_pep()
    if not caminho_final:
        return None

    nome_norm = normalizar_texto(nome_input)
    if not nome_norm or len(nome_norm.split()) < 2:
        return None

    cpf_numeros = re.sub(r'\D', '', cpf_input)
    miolo_cpf = cpf_numeros[3:9] if len(cpf_numeros) == 11 else ""

    try:
        with open(caminho_final, mode='r', encoding='utf-8', errors='ignore') as f:
            primeira_linha = f.readline()
            sep = ';' if ';' in primeira_linha else (',' if ',' in primeira_linha else '\t')
            f.seek(0)

            reader = csv.DictReader(f, delimiter=sep)
            for row in reader:
                nome_pep_row = row.get('Nome_PEP') or row.get('NOME_PEP') or row.get('Nome') or row.get('NOME') or ""
                nome_pep_norm = normalizar_texto(nome_pep_row)

                if nome_norm == nome_pep_norm:
                    cpf_row = row.get('CPF') or row.get('Cpf') or row.get('CPF_PEP') or ""
                    cpf_row_numeros = re.sub(r'\D', '', cpf_row)

                    if miolo_cpf and cpf_row_numeros and len(cpf_row_numeros) == 11:
                        if miolo_cpf != cpf_row_numeros[3:9]:
                            continue

                    cargo = row.get('Descrição_Função') or row.get('DESCRICAO_FUNCAO') or row.get('Função') or row.get('Cargo') or "Agente Político / Função Pública"
                    orgao = row.get('Nome_Órgão') or row.get('NOME_ORGAO') or row.get('Órgão') or row.get('Orgao') or "Administração Pública (CGU)"

                    return {
                        "cargo": cargo.strip(),
                        "orgao": orgao.strip(),
                        "detalhe": f"Registro Oficial na Base da CGU ({caminho_final})"
                    }
    except Exception:
        pass

    return None

def buscar_wikipedia(nome):
    """Busca resumo da autoridade na Wikipédia em Português."""
    try:
        url = "https://pt.wikipedia.org/w/api.php"
        params = {
            "action": "query",
            "format": "json",
            "prop": "extracts",
            "exintro": True,
            "explaintext": True,
            "titles": nome
        }
        res = requests.get(url, params=params, timeout=4).json()
        pages = res.get("query", {}).get("pages", {})
        for page_id, page_data in pages.items():
            if page_id != "-1":
                return page_data.get("extract", "")
    except Exception:
        pass
    return ""

def analisar_proximidade_cargo(texto_bruto, nome_pesquisado):
    """Analisa se o nome pesquisado aparece vinculado a um cargo público relevante."""
    texto_norm = normalizar_texto(texto_bruto)
    nome_norm = normalizar_texto(nome_pesquisado)

    if nome_norm not in texto_norm:
        return None

    cargos_pep = [
        "senador", "senadora", "deputado", "deputada", "governador", "governadora", 
        "prefeito", "prefeita", "ministro", "ministra", "desembargador", "desembargadora", 
        "juiz", "juiza", "juiz federal", "procurador", "procuradora", "secretario", 
        "secretaria", "vereador", "vereadora", "magistrado", "magistrada", "parlamentar", 
        "ex ministro", "ex senador", "ex deputado", "ex governador", "ex prefeito", "politico", "politica"
    ]

    indices_nome = [m.start() for m in re.finditer(re.escape(nome_norm), texto_norm)]

    for idx in indices_nome:
        inicio_janela = max(0, idx - 250)
        fim_janela = min(len(texto_norm), idx + len(nome_norm) + 250)
        trecho = texto_norm[inicio_janela:fim_janela]

        for cargo in cargos_pep:
            if cargo in trecho:
                return cargo.title()

    return None

# -----------------------------------------------------------------------------
# 🔑 CONFIGURAÇÃO DE ACESSO E AUTENTICAÇÃO
# -----------------------------------------------------------------------------
SENHA_GERAL = "Bks2026@"

st.set_page_config(
    page_title="PLD/FTP - BKS Compliance", 
    page_icon="🛡️", 
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    h1 { color: #0056b3; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; font-weight: 700; margin-bottom: 0px; }
    div.stButton > button:first-child { background-color: #0056b3; color: white; font-weight: bold; border-radius: 6px; border: none; padding: 12px 24px; transition: all 0.3s ease; }
    div.stButton > button:first-child:hover { background-color: #003366; box-shadow: 0 4px 8px rgba(0,0,0,0.15); }
    </style>
""", unsafe_allow_html=True)

if "autenticado" not in st.session_state:
    st.session_state.autenticado = False
if "email_logado" not in st.session_state:
    st.session_state.email_logado = None
if "renovar_nome" not in st.session_state:
    st.session_state.renovar_nome = ""
if "renovar_cpf" not in st.session_state:
    st.session_state.renovar_cpf = ""

if not st.session_state.autenticado:
    col_l1, col_l2, col_l3 = st.columns([1, 2, 1])
    with col_l2:
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.image("logo_bks.png" if os.path.exists("logo_bks.png") else "https://via.placeholder.com/300x80?text=BKS+Compliance", width=260)
        st.title("🛡️ Acesso ao Painel PLD/FTP")
        st.caption("Sistema de Conformidade e Prevenção à Lavagem de Dinheiro")
        st.markdown("---")
        
        email_digitado = st.text_input("📧 E-mail do Operador:", placeholder="seu.nome@bks.com.br").strip().lower()
        senha_digitada = st.text_input("🔑 Senha de Acesso:", type="password")
        
        if st.button("🔓 Entrar no Sistema", use_container_width=True):
            if senha_digitada == SENHA_GERAL:
                if not email_digitado:
                    email_digitado = "operacao@bks.com.br"
                
                st.session_state.autenticado = True
                st.session_state.email_logado = email_digitado
                st.rerun()
            else:
                st.error("❌ Senha incorreta! Verifique seus dados de acesso.")
    st.stop()

# -----------------------------------------------------------------------------
# 🛡️ BARRA LATERAL (SIDEBAR) & NAVEGAÇÃO
# -----------------------------------------------------------------------------
with st.sidebar:
    if os.path.exists("logo_bks.png"):
        st.image("logo_bks.png", use_container_width=True)
    elif os.path.exists("logo_bksre.png"):
        st.image("logo_bksre.png", use_container_width=True)
    
    st.markdown("### 🟢 Status: **Operacional**")
    st.caption("BKS Corretora & BKS Re Resseguros")
    st.markdown("---")
    st.markdown(f"📧 **E-mail:** {st.session_state.email_logado}")
    st.markdown("---")
    
    # Se houver pedido de renovação pendente, força a navegação para a tela de busca
    if st.session_state.renovar_nome:
        index_menu = 0
    else:
        index_menu = 0

    opcao_menu = st.radio(
        "📌 Menu de Navegação:",
        ["🔍 Consulta PLD/FTP", "📊 Gestão de Vencimentos"],
        index=index_menu
    )
    
    st.markdown("---")
    
    arquivo_encontrado = identificar_arquivo_pep()
    if arquivo_encontrado:
        data_arquivo = datetime(2026, 8, 14)
        dias_desde_atualizacao = (datetime.now() - data_arquivo).days

        if dias_desde_atualizacao > 30:
            st.warning(f"⚠️ **Base PEP Local:** Atualização Necessária!\n(Inclusão de {data_arquivo.strftime('%d/%m/%Y')} - há {dias_desde_atualizacao} dias)")
            st.caption("💡 *Recomendado baixar a nova base no Portal da Transparência (CGU) e atualizar no GitHub.*")
        else:
            st.success("📁 **Base PEP Local:** Carregada e Ativa")
            st.caption(f"🗓️ *Inclusão da base: {data_arquivo.strftime('%d/%m/%Y')}*")
    else:
        st.info("🌐 **Base PEP Local:** Não enc. (Modo Web Ativo)")

    st.markdown("---")
    st.markdown("### 🏛️ Consultas Receita Federal")
    st.link_button("📄 Consulta CPF (Receita)", "https://servicos.receita.fazenda.gov.br/Servicos/CPF/ConsultaSituacao/ConsultaPublica.asp", use_container_width=True)
    st.link_button("🏢 Consulta CNPJ (Receita)", "https://solucoes.receita.fazenda.gov.br/Servicos/cnpjreva/cnpjreva_solicitacao.asp", use_container_width=True)
    st.markdown("---")
    
    if st.button("🔒 Sair do Sistema", use_container_width=True):
        st.session_state.autenticado = False
        st.session_state.email_logado = None
        st.session_state.renovar_nome = ""
        st.session_state.renovar_cpf = ""
        st.rerun()

# =============================================================================
# 📌 TELA 1: CONSULTA PLD/FTP
# =============================================================================
if opcao_menu == "🔍 Consulta PLD/FTP":
    st.title("🛡️ Painel Oficial de Consulta PLD/FTP")
    st.caption("Pesquisa automatizada em portais de transparência e bases públicas para enquadramento regulatório.")
    st.markdown("<br>", unsafe_allow_html=True)

    # Preenchimento automático caso venha de um clique em "Renovar"
    val_nome_def = st.session_state.renovar_nome if st.session_state.renovar_nome else ""
    val_cpf_def = st.session_state.renovar_cpf if st.session_state.renovar_cpf else ""

    with st.container():
        st.markdown("### 📋 Dados do Pesquisado")
        col1, col2 = st.columns(2)
        with col1:
            nome_input = st.text_input("👉 Nome Completo do Pesquisado", value=val_nome_def, placeholder="Ex: João da Silva")
        with col2:
            cpf_input = st.text_input("👉 CPF do Pesquisado", value=val_cpf_def, placeholder="Ex: 000.000.000-00")

        st.markdown("<br>", unsafe_allow_html=True)
        btn_pesquisar = st.button("🔎 Iniciar Consulta e Gerar Relatório PDF", type="primary", use_container_width=True)

    if btn_pesquisar or (st.session_state.renovar_nome and st.session_state.renovar_cpf):
        # Limpa os estados do clique de renovação após engatar a busca
        st.session_state.renovar_nome = ""
        st.session_state.renovar_cpf = ""
        
        cpf_valido_bool = validar_cpf(cpf_input)
        
        if not nome_input.strip():
            st.warning("⚠️ Por favor, preencha o Nome Completo antes de continuar.")
        elif not cpf_valido_bool:
            st.error("❌ **CPF Inválido:** O CPF informado possui erro nos dígitos verificadores ou formato incorreto. Corrija o número para prosseguir.")
        else:
            with st.spinner("🔎 Consultando base oficial e realizando varredura web de governança..."):
                
                nome_limpo = nome_input.strip()
                
                match_planilha = buscar_na_planilha_pep(nome_limpo, cpf_input)
                
                if match_planilha:
                    detec_pep = True
                    origem_identificacao = f"Base Oficial de PEPs ({match_planilha['detalhe']})"
                    cargo_detectado = match_planilha["cargo"]
                    orgao_detectado = match_planilha["orgao"]
                    detalhe_cargo = "Cadastro Ativo na Base Oficial do Governo Federal (CGU)"
                else:
                    origem_identificacao = "Pesquisa em Portais Públicos e Notícias Web"
                    
                    wiki_text = buscar_wikipedia(nome_limpo)
                    cargo_wiki = analisar_proximidade_cargo(wiki_text, nome_limpo)

                    if cargo_wiki:
                        detec_pep = True
                        cargo_detectado = f"Agente Político / Notória Exposição ({cargo_wiki})"
                        orgao_detectado = "Administração Pública / Registro Histórico (Wikipédia)"
                        detalhe_cargo = "Histórico Mapeado na Wikipédia Brasil"
                    else:
                        res_web = ""
                        queries_estritas = [
                            f'"{nome_limpo}" cargo politico',
                            f'"{nome_limpo}" senador OR deputado OR prefeito OR ministro OR vereador OR juiz'
                        ]
                        try:
                            with DDGS() as ddgs:
                                for q in queries_estritas:
                                    results = list(ddgs.text(q, max_results=3))
                                    for r in results:
                                        res_web += f"{r.get('title', '')} {r.get('body', '')}\n"
                        except Exception:
                            pass

                        cargo_web = analisar_proximidade_cargo(res_web, nome_limpo)
                        
                        if cargo_web:
                            detec_pep = True
                            cargo_detectado = f"Agente Político / Exposição Pública ({cargo_web})"
                            orgao_detectado = "Administração Pública"
                            detalhe_cargo = "Histórico Mapeado em Portais Públicos e Notícias Web"
                        else:
                            detec_pep = False

                SITUACAO_CPF = "VÁLIDO"
                tz_bsb = timezone(timedelta(hours=-3))
                agora_dt = datetime.now(tz_bsb)

                if detec_pep:
                    STATUS_PEP = "SIM"
                    PEP_VINCULO = "NÃO CONSTA"
                    CARGOS_EXERCIDOS = cargo_detectado
                    ORGAO_ENTIDADE = orgao_detectado
                    DETALHE_EXPOSICAO = detalhe_cargo
                    RISCO_FINAL = "ALTO RISCO"
                    PRAZO_RENOVAÇÃO = "06 MESES"
                    APONTAMENTOS = f"RESTRIÇÃO: Exposição ativa ou histórico em alta função pública / PEP ({origem_identificacao})"
                    PERFIL_OP = "Pessoa Politicamente Exposta (PEP)"
                    PARECER = f"Identificado enquadramento regulatório de PEP ({cargo_detectado}). Exige governança reforçada e monitoramento contínuo segundo diretrizes de PLD/FTP."
                    PROXIMA_ATUALIZACAO = (agora_dt + timedelta(days=180)).strftime('%d/%m/%Y')
                else:
                    STATUS_PEP = "NÃO"
                    PEP_VINCULO = "NÃO CONSTA"
                    CARGOS_EXERCIDOS = "Nenhum cargo público detectado"
                    ORGAO_ENTIDADE = "Sem vínculo identificado"
                    DETALHE_EXPOSICAO = "Sem histórico de exposição pública registrado"
                    RISCO_FINAL = "BAIXO"
                    PRAZO_RENOVAÇÃO = "01 ANO"
                    APONTAMENTOS = "SEM RESTRIÇÕES: Nada consta na base oficial da CGU nem nos portais de transparência"
                    PERFIL_OP = "Profissional Independente"
                    PARECER = "Consulta realizada na base oficial de transparência da CGU e portais públicos. Não foram identificados cargos políticos ativos nem histórico de exposição pública para o Nome e CPF informados."
                    PROXIMA_ATUALIZACAO = (agora_dt + timedelta(days=365)).strftime('%d/%m/%Y')

                # REGISTRA OU ATUALIZA O VENCIMENTO (SEM DUPLICAR)
                registrar_vencimento(
                    nome=nome_input,
                    cpf=cpf_input,
                    email_operador=st.session_state.email_logado,
                    status_pep=STATUS_PEP,
                    data_emissao_dt=agora_dt,
                    data_vencimento_str=PROXIMA_ATUALIZACAO
                )

                st.markdown("---")
                if STATUS_PEP == "SIM":
                    st.error(f"🔴 **RESULTADO: PESSOA POLITICAMENTE EXPOSTA (PEP)** | Cargo: {CARGOS_EXERCIDOS} | Origem: {origem_identificacao}")
                else:
                    st.success("🟢 **RESULTADO: NADA CONSTA (NÃO É PEP)**")

                buffer = io.BytesIO()
                doc = SimpleDocTemplate(
                    buffer, pagesize=A4, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=45
                )

                story = []
                styles = getSampleStyleSheet()

                style_title = ParagraphStyle('Title', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=12, leading=14, alignment=TA_CENTER, textColor=colors.HexColor('#0056b3'))
                style_meta_val = ParagraphStyle('MetaVal', parent=styles['Normal'], fontName='Helvetica', fontSize=7, leading=10, alignment=TA_CENTER, textColor=colors.HexColor('#212529'))
                style_sec = ParagraphStyle('SecTitle', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=9, leading=11, textColor=colors.white)
                style_lbl = ParagraphStyle('Label', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=7, leading=9, textColor=colors.HexColor('#555555'))
                style_val = ParagraphStyle('Value', parent=styles['Normal'], fontName='Helvetica', fontSize=8, leading=10, textColor=colors.HexColor('#212529'))
                style_badge_txt = ParagraphStyle('BadgeTxt', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=7.5, leading=9, alignment=TA_CENTER, textColor=colors.white)
                style_alert_gerencia = ParagraphStyle('AlertGerencia', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=8, leading=11, alignment=TA_CENTER, textColor=colors.HexColor('#dc3545'))
                style_disclaimer = ParagraphStyle('Disclaimer', parent=styles['Normal'], fontName='Helvetica-Oblique', fontSize=7, leading=9, alignment=TA_CENTER, textColor=colors.HexColor('#555555'))
                style_date = ParagraphStyle('DateEmis', parent=styles['Normal'], fontName='Helvetica-Oblique', fontSize=7, leading=9, alignment=TA_RIGHT, textColor=colors.HexColor('#444444'))

                def format_val(key, text):
                    u = text.strip().upper()
                    if key in ['STATUS_PEP', 'RISCO_FINAL', 'PRAZO_RENOVAÇÃO']:
                        bg_col = "#28a745"
                        if u in ['SIM', 'ALTO RISCO', '06 MESES']:
                            bg_col = "#dc3545"
                        elif u in ['MÉDIO RISCO']:
                            bg_col = "#ffc107"

                        txt_p = Paragraph(text, style_badge_txt)
                        calc_w = max(len(text) * 6.5, 45)
                        t_badge = Table([[txt_p]], colWidths=[calc_w])
                        t_badge.setStyle(TableStyle([
                            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor(bg_col)),
                            ('TOPPADDING', (0,0), (-1,-1), 2.5),
                            ('BOTTOMPADDING', (0,0), (-1,-1), 2.5),
                            ('LEFTPADDING', (0,0), (-1,-1), 4),
                            ('RIGHTPADDING', (0,0), (-1,-1), 4),
                            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                        ]))
                        return t_badge
                    return Paragraph(text, style_val)

                def load_proportional_img(path, target_h=65):
                    if path and os.path.exists(path):
                        try:
                            with PILImage.open(path) as p_img:
                                w, h = p_img.size
                                aspect = w / float(h)
                                new_w = target_h * aspect
                                return Image(path, width=new_w, height=target_h)
                        except Exception:
                            pass
                    return None

                path_l1 = "logo_bks.png" if os.path.exists("logo_bks.png") else None
                path_l2 = "logo_bksre.png" if os.path.exists("logo_bksre.png") else None

                img1 = load_proportional_img(path_l1, 65) or Paragraph("<b>BKS CORRETORA</b>", style_title)
                img2 = load_proportional_img(path_l2, 65) or Paragraph("<b>BKS RE RESSEGUROS</b>", style_title)

                t_header = Table([[img1, "", img2]], colWidths=[230, 62, 230])
                t_header.setStyle(TableStyle([
                    ('ALIGN', (0,0), (0,0), 'LEFT'),
                    ('ALIGN', (2,0), (2,0), 'RIGHT'),
                    ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ]))
                story.append(t_header)
                story.append(Spacer(1, 16))

                story.append(Paragraph("RELATÓRIO DE CONSULTA E CONFORMIDADE (PLD/FTP)", style_title))
                story.append(Spacer(1, 10))

                emissor_nome = f"Operador: {st.session_state.email_logado}"
                meta_table_data = [
                    [Paragraph(f"Emissor: {emissor_nome}", style_meta_val)],
                    [Paragraph("Status: CONCLUÍDO &nbsp;|&nbsp; Classificação: CONFIDENCIAL", style_meta_val)]
                ]
                
                t_meta = Table(meta_table_data, colWidths=[522])
                t_meta.setStyle(TableStyle([
                    ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#f8f9fa')),
                    ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#d0d7de')),
                    ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor('#e1e4e8')),
                    ('TOPPADDING', (0,0), (-1,-1), 4),
                    ('BOTTOMPADDING', (0,0), (-1,-1), 4),
                ]))
                story.append(t_meta)
                story.append(Spacer(1, 16))

                def make_sec(title, fields, full_banner_alert=None):
                    t_sec_title = Table([[Paragraph(title, style_sec)]], colWidths=[522])
                    t_sec_title.setStyle(TableStyle([
                        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#0056b3')),
                        ('TOPPADDING', (0,0), (-1,-1), 4),
                        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
                        ('LEFTPADDING', (0,0), (-1,-1), 8),
                    ]))
                    story.append(t_sec_title)

                    table_data = []
                    for i in range(0, len(fields), 2):
                        f1 = fields[i]
                        f2 = fields[i+1] if i+1 < len(fields) else None
                        
                        c1 = [Paragraph(f1[0], style_lbl), format_val(f1[2] if len(f1)>2 else '', f1[1])]
                        c2 = [Paragraph(f2[0], style_lbl), format_val(f2[2] if len(f2)>2 else '', f2[1])] if f2 else ["", ""]
                        
                        table_data.append([c1, c2])

                    t_content = Table(table_data, colWidths=[261, 261])
                    t_content.setStyle(TableStyle([
                        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#f4f6f8')),
                        ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#d0d7de')),
                        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor('#d0d7de')),
                        ('TOPPADDING', (0,0), (-1,-1), 5),
                        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
                        ('LEFTPADDING', (0,0), (-1,-1), 8),
                        ('RIGHTPADDING', (0,0), (-1,-1), 8),
                        ('VALIGN', (0,0), (-1,-1), 'TOP'),
                    ]))
                    story.append(t_content)

                    if full_banner_alert:
                        p_alert = Paragraph(full_banner_alert, style_alert_gerencia)
                        t_alert = Table([[p_alert]], colWidths=[522])
                        t_alert.setStyle(TableStyle([
                            ('BACKGROUND', (0,0), (-1,-1), colors.white),
                            ('BOX', (0,0), (-1,-1), 1.2, colors.HexColor('#dc3545')),
                            ('TOPPADDING', (0,0), (-1,-1), 6),
                            ('BOTTOMPADDING', (0,0), (-1,-1), 6),
                            ('LEFTPADDING', (0,0), (-1,-1), 10),
                            ('RIGHTPADDING', (0,0), (-1,-1), 10),
                            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                        ]))
                        story.append(t_alert)

                    story.append(Spacer(1, 8))

                make_sec("1. DADOS QUALIFICATIVOS DO PESQUISADO", [
                    ("NOME COMPLETO", nome_input.upper()),
                    ("CPF", cpf_input),
                    ("PERFIL E NATUREZA", "Pessoa Física"),
                    ("CARGO / EXPOSIÇÃO", CARGOS_EXERCIDOS)
                ])

                make_sec("2. CLASSIFICAÇÃO DE RISCO E DETALHES DO CARGO PÚBLICO", [
                    ("STATUS PEP DIRETO", STATUS_PEP, "STATUS_PEP"),
                    ("STATUS POR VÍNCULO", PEP_VINCULO),
                    ("ÓRGÃO / ENTIDADE DE ATUAÇÃO", ORGAO_ENTIDADE),
                    ("ENQUADRAMENTO DO CARGO", DETALHE_EXPOSICAO)
                ])

                make_sec("3. MAPEAMENTO DE VÍNCULOS FAMILIARES E EMPRESARIAIS", [
                    ("RELAÇÃO 2º GRAU PEP", "Sem vínculos mapeados"),
                    ("SOCIEDADES E PARTICIPAÇÕES", "Sem restrições ativas")
                ])

                make_sec("4. PERFIL EMPRESARIAL E SETOR DE ATUAÇÃO (RISCO OPERACIONAL)", [
                    ("PERFIL OPERACIONAL", PERFIL_OP),
                    ("REGIÃO DE ATUAÇÃO", "Brasil"),
                    ("SITUAÇÃO CADASTRAL CPF", SITUACAO_CPF),
                    ("APONTAMENTOS / RESTRIÇÕES", APONTAMENTOS)
                ])

                alerta_gerencia = "Obrigatório solicitar aprovação da gerência antes de prosseguir com as tratativas de seguro." if STATUS_PEP == "SIM" else None

                make_sec("5. CONCLUSÃO E RECOMENDAÇÕES DE GOVERNANÇA", [
                    ("NÍVEL DE RISCO FINAL", RISCO_FINAL, "RISCO_FINAL"),
                    ("PARECER DE CONFORMIDADE", PARECER)
                ], full_banner_alert=alerta_gerencia)

                make_sec("6. RENOVAÇÃO DE RELATÓRIO", [
                    ("PRAZO EXIGIDO PARA REVISÃO", PRAZO_RENOVAÇÃO, "PRAZO_RENOVAÇÃO"),
                    ("PRÓXIMA ATUALIZACAO RECOMENDADA", PROXIMA_ATUALIZACAO)
                ])

                story.append(Spacer(1, 16))
                disclaimer_txt = "Os dados de terceiros foram obtidos de fontes consideradas confiáveis, mas não nos responsabilizamos por eventuais erros, omissões ou desatualizações presentes na origem das informações."
                story.append(Paragraph(disclaimer_txt, style_disclaimer))
                story.append(Spacer(1, 10))
                
                hora_agora_bsb = agora_dt.strftime('%d/%m/%Y às %H:%M:%S')
                story.append(Paragraph(f"<b>Relatório emitido em:</b> {hora_agora_bsb}", style_date))

                def add_footer(canvas, doc):
                    canvas.saveState()
                    ft_text = "Documento gerado pelo sistema interno de Compliance - BKS Corretora de Seguros Ltda. & BKS Re Corretora de Resseguros Ltda."
                    canvas.setFont("Helvetica", 7)
                    canvas.setFillColor(colors.HexColor('#777777'))
                    canvas.drawCentredString(A4[0] / 2.0, 20, ft_text)
                    canvas.restoreState()

                doc.build(story, onFirstPage=add_footer, onLaterPages=add_footer)
                pdf_bytes = buffer.getvalue()

                st.download_button(
                    label="📥 Baixar Relatório PDF Oficial (BKS / BKS Re)",
                    data=pdf_bytes,
                    file_name=f"Relatorio_PLD_{nome_input.replace(' ', '_').upper()}.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )

# =============================================================================
# 📊 TELA 2: GESTÃO DE VENCIMENTOS DOS RELATÓRIOS
# =============================================================================
elif opcao_menu == "📊 Gestão de Vencimentos":
    st.title("📊 Gestão de Vencimentos de Relatórios PLD/FTP")
    st.caption("Acompanhamento contínuo dos prazos de renovação e governança regulatória.")
    st.markdown("<br>", unsafe_allow_html=True)

    registros = carregar_vencimentos()

    if not registros:
        st.info("ℹ️ Nenhum relatório foi registrado até o momento.")
    else:
        hoje_dt = datetime.now()
        
        vencidos = 0
        a_vencer_breve = 0
        validos = 0
        
        dados_processados = []
        for reg in registros:
            try:
                dt_venc = datetime.strptime(reg["Data_Vencimento"], "%d/%m/%Y")
                dias_restantes = (dt_venc - hoje_dt).days
                
                if dias_restantes < 0:
                    status_alerta = "🔴 Vencido"
                    vencidos += 1
                elif dias_restantes <= 30:
                    status_alerta = "🟡 Vence em breve"
                    a_vencer_breve += 1
                else:
                    status_alerta = "🟢 Válido"
                    validos += 1
            except Exception:
                status_alerta = "⚪ Indefinido"

            dados_processados.append({
                "Nome Completo": reg.get("Nome", ""),
                "CPF": reg.get("CPF", ""),
                "Status PEP": reg.get("Status_PEP", ""),
                "Data de Emissão": reg.get("Data_Emissao", ""),
                "Data de Vencimento": reg.get("Data_Vencimento", ""),
                "Status do Prazo": status_alerta,
                "Operador": reg.get("Operador", "")
            })

        # METRICAS
        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        col_m1.metric("Total de Relatórios", len(registros))
        col_m2.metric("🟢 Dentro do Prazo", validos)
        col_m3.metric("🟡 Vencem em até 30 dias", a_vencer_breve)
        col_m4.metric("🔴 Vencidos / Expirados", vencidos)

        st.markdown("---")
        st.subheader("🔍 Filtros de Busca")

        # FILTROS
        col_f1, col_f2 = st.columns([1, 2])
        with col_f1:
            filtro_status = st.selectbox(
                "Filtrar por Status do Prazo:",
                ["Todos", "🔴 Apenas Vencidos", "🟡 Vencem em breve", "🟢 Apenas Válidos"]
            )
        with col_f2:
            termo_busca = st.text_input("Buscar por Nome ou CPF:", placeholder="Digite o nome ou CPF...")

        # APLICA FILTROS
        dados_filtrados = []
        for item in dados_processados:
            # Filtro de Status
            if filtro_status == "🔴 Apenas Vencidos" and "🔴" not in item["Status do Prazo"]:
                continue
            elif filtro_status == "🟡 Vencem em breve" and "🟡" not in item["Status do Prazo"]:
                continue
            elif filtro_status == "🟢 Apenas Válidos" and "🟢" not in item["Status do Prazo"]:
                continue

            # Filtro de Texto
            if termo_busca:
                tb_norm = normalizar_texto(termo_busca)
                nome_norm = normalizar_texto(item["Nome Completo"])
                cpf_limpo = re.sub(r'\D', '', item["CPF"])
                tb_limpo = re.sub(r'\D', '', termo_busca)
                if tb_norm not in nome_norm and (tb_limpo == "" or tb_limpo not in cpf_limpo):
                    continue

            dados_filtrados.append(item)

        st.markdown("<br>", unsafe_allow_html=True)
        st.subheader("📋 Relatórios Cadastrados")

        if not dados_filtrados:
            st.warning("Nenhum registro localizado com os filtros selecionados.")
        else:
            # EXIBIÇÃO INTERATIVA COM BOTAO RENOVAR
            for idx, item in enumerate(dados_filtrados):
                c_n, c_c, c_p, c_e, c_v, c_s, c_b = st.columns([2.5, 1.3, 1, 1.5, 1.2, 1.2, 1])
                
                with c_n:
                    st.write(f"**{item['Nome Completo']}**")
                with c_c:
                    st.write(item["CPF"])
                with c_p:
                    st.write(item["Status PEP"])
                with c_e:
                    st.write(item["Data de Emissão"])
                with c_v:
                    st.write(item["Data de Vencimento"])
                with c_s:
                    st.write(item["Status do Prazo"])
                with c_b:
                    if st.button("🔄 Renovar", key=f"btn_renovar_{idx}"):
                        st.session_state.renovar_nome = item["Nome Completo"]
                        st.session_state.renovar_cpf = item["CPF"]
                        st.rerun()
                st.divider()

        st.markdown("<br>", unsafe_allow_html=True)

        # BOTAO PARA EXPORTAR PARA EXCEL EM COLUNAS SEPARADAS (DELIMITADOR ';')
        csv_buffer = io.StringIO()
        campos = ["Nome Completo", "CPF", "Status PEP", "Data de Emissão", "Data de Vencimento", "Status do Prazo", "Operador"]
        writer = csv.DictWriter(csv_buffer, fieldnames=campos, delimiter=';')
        writer.writeheader()
        writer.writerows(dados_filtrados if dados_filtrados else dados_processados)

        st.download_button(
            label="📥 Exportar Lista em Colunas (.CSV para Excel)",
            data=csv_buffer.getvalue().encode('utf-8-sig'),
            file_name=f"Controle_Vencimentos_PLD_BKS_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
            use_container_width=True
        )
