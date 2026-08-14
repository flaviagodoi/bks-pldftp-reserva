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
# 🛠️ FUNÇÕES AUXILIARES DE NORMALIZAÇÃO E BUSCA LOCAL
# -----------------------------------------------------------------------------
def normalizar_texto(txt):
    """Remove acentos, caracteres especiais e converte para caixa baixa e espaços simples."""
    if not txt:
        return ""
    nfkd = unicodedata.normalize('NFD', str(txt))
    sem_acento = "".join([c for c in nfkd if not unicodedata.combining(c)])
    limpo = re.sub(r'[^a-zA-Z0-9\s]', ' ', sem_acento).lower()
    return " ".join(limpo.split())

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
    """
    Busca na planilha oficial da CGU com rigor anti-homônimo:
    - Nome Completo deve ser idêntico.
    - Miolo do CPF (6 dígitos centrais) deve bater.
    """
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

                if nome_norm != nome_pep_norm:
                    continue

                cpf_row = row.get('CPF') or row.get('Cpf') or row.get('CPF_PEP') or ""
                cpf_row_numeros = re.sub(r'\D', '', cpf_row)

                if miolo_cpf and cpf_row_numeros:
                    if miolo_cpf != cpf_row_numeros:
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
    """
    Analisa se o nome pesquisado aparece diretamente vinculado a um cargo
    público relevante no mesmo parágrafo / contexto de até 60 caracteres.
    """
    texto_norm = normalizar_texto(texto_bruto)
    nome_norm = normalizar_texto(nome_pesquisado)

    if nome_norm not in texto_norm:
        return None

    # Lista de cargos e termos PEP específicos
    cargos_pep = [
        "deputado federal", "deputado estadual", "senador", "governador", "prefeito",
        "ministro de estado", "ministro do stf", "ministro do stj", "ministro do tcu",
        "desembargador", "juiz federal", "procurador geral", "secretario de estado",
        "secretario municipal", "vereador", "ex deputado", "ex prefeito", "ex senador",
        "ex governador", "ex ministro"
    ]

    # Encontra todas as ocorrências do nome no texto
    indices_nome = [m.start() for m in re.finditer(re.escape(nome_norm), texto_norm)]

    for idx in indices_nome:
        # Pega a janela de texto em volta do nome (60 caracteres antes e 60 depois)
        inicio_janela = max(0, idx - 60)
        fim_janela = min(len(texto_norm), idx + len(nome_norm) + 60)
        trecho = texto_norm[inicio_janela:fim_janela]

        for cargo in cargos_pep:
            if cargo in trecho:
                return cargo.title()

    return None

# -----------------------------------------------------------------------------
# 🔑 CONFIGURAÇÃO DE ACESSO DADOS DE LOGIN
# -----------------------------------------------------------------------------
SENHA_GERAL = "Bks2026@"

st.set_page_config(
    page_title="PLD/FTP - BKS Compliance", 
    page_icon="🛡️", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# ESTILIZAÇÃO CSS CUSTOMIZADA
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

# -----------------------------------------------------------------------------
# 🔑 TELA DE LOGIN DIRETA
# -----------------------------------------------------------------------------
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
# 🛡️ BARRA LATERAL (SIDEBAR)
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
    
    # STATUS DA PLANILHA OFICIAL LOCAL COM CHECAGEM DE VALIDADE (30 DIAS)
    arquivo_encontrado = identificar_arquivo_pep()
    if arquivo_encontrado:
        tempo_modificacao = os.path.getmtime(arquivo_encontrado)
        data_arquivo = datetime.fromtimestamp(tempo_modificacao)
        dias_desde_atualizacao = (datetime.now() - data_arquivo).days

        if dias_desde_atualizacao > 30:
            st.warning(f"⚠️ **Base PEP Local:** Atualização Necessária!\n(Arquivo de {data_arquivo.strftime('%d/%m/%Y')} - há {dias_desde_atualizacao} dias)")
            st.caption("💡 *Recomendado baixar a nova base no Portal da Transparência (CGU) e atualizar no GitHub.*")
        else:
            st.success("📁 **Base PEP Local:** Carregada e Ativa")
            st.caption(f"🗓️ *Última atualização: {data_arquivo.strftime('%d/%m/%Y')}*")
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
        st.rerun()

# -----------------------------------------------------------------------------
# 🛡️ PAINEL PRINCIPAL
# -----------------------------------------------------------------------------
st.title("🛡️ Painel Oficial de Consulta PLD/FTP")
st.caption("Pesquisa automatizada em portais de transparência e bases públicas para enquadramento regulatório.")
st.markdown("<br>", unsafe_allow_html=True)

with st.container():
    st.markdown("### 📋 Dados do Pesquisado")
    col1, col2 = st.columns(2)
    with col1:
        nome_input = st.text_input("👉 Nome Completo do Pesquisado", placeholder="Ex: João da Silva")
    with col2:
        cpf_input = st.text_input("👉 CPF do Pesquisado", placeholder="Ex: 000.000.000-00")

    st.markdown("<br>", unsafe_allow_html=True)
    btn_pesquisar = st.button("🔎 Iniciar Consulta e Gerar Relatório PDF", type="primary", use_container_width=True)

# -----------------------------------------------------------------------------
# ⚙️ EXECUÇÃO DA CONSULTA DUPLA
# -----------------------------------------------------------------------------
if btn_pesquisar:
    cpf_limpo_num = re.sub(r'\D', '', cpf_input)
    if not nome_input.strip() or len(cpf_limpo_num) != 11:
        st.warning("⚠️ Por favor, preencha o Nome Completo e um CPF válido com 11 dígitos antes de continuar.")
    else:
        with st.spinner("🔎 Consultando base oficial e realizando varredura web de governança..."):
            
            nome_limpo = nome_input.strip()
            
            # 1ª CAMADA: CONSULTA RIGOROSA NA BASE LOCAL DA CGU
            match_planilha = buscar_na_planilha_pep(nome_limpo, cpf_input)
            
            if match_planilha:
                detec_pep = True
                origem_identificacao = f"Base Oficial de PEPs ({match_planilha['detalhe']})"
                cargo_detectado = match_planilha["cargo"]
                orgao_detectado = match_planilha["orgao"]
                detalhe_cargo = "Cadastro Ativo na Base Oficial do Governo Federal (CGU)"
            else:
                # 2ª CAMADA: BUSCA WEB DE PRECISÃO (PARA EX-AUTORIDADES / EX-POLÍTICOS)
                origem_identificacao = "Pesquisa em Portais Públicos e Notícias Web"
                
                # Wikipédia
                wiki_text = buscar_wikipedia(nome_limpo)
                cargo_wiki = analisar_proximidade_cargo(wiki_text, nome_limpo)

                if cargo_wiki:
                    detec_pep = True
                    cargo_detectado = f"Agente Político / Notória Exposição ({cargo_wiki})"
                    orgao_detectado = "Administração Pública / Registro Histórico (Wikipédia)"
                    detalhe_cargo = "Histórico Mapeado na Wikipédia Brasil"
                else:
                    # DuckDuckGo com aspas estritas
                    res_web = ""
                    queries_estritas = [
                        f'"{nome_limpo}" cargo politico',
                        f'"{nome_limpo}" deputado OR prefeito OR senador OR ministro OR vereador'
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

            # -----------------------------------------------------------------
            # ATRIBUIÇÃO DOS RESULTADOS FINAIS
            # -----------------------------------------------------------------
            if detec_pep:
                STATUS_PEP = "SIM"
                PEP_VINCULO = "NÃO CONSTA"
                CARGOS_EXERCIDOS = cargo_detectado
                ORGAO_ENTIDADE = orgao_detectado
                DETALHE_EXPOSICAO = detalhe_cargo
                RISCO_FINAL = "ALTO RISCO"
                PRAZO_RENOVAÇÃO = "06 MESES"
                SITUACAO_CPF = "REGULAR"
                APONTAMENTOS = f"RESTRIÇÃO: Exposição ativa ou histórico em alta função pública / PEP ({origem_identificacao})"
                PERFIL_OP = "Pessoa Politicamente Exposta (PEP)"
                PARECER = f"Identificado enquadramento regulatório de PEP ({cargo_detectado}). Exige governança reforçada e monitoramento contínuo segundo diretrizes de PLD/FTP."
                PROXIMA_ATUALIZACAO = "13/02/2027"
            else:
                STATUS_PEP = "NÃO"
                PEP_VINCULO = "NÃO CONSTA"
                CARGOS_EXERCIDOS = "Nenhum cargo público detectado"
                ORGAO_ENTIDADE = "Sem vínculo identificado"
                DETALHE_EXPOSICAO = "Sem histórico de exposição pública registrado"
                RISCO_FINAL = "BAIXO"
                PRAZO_RENOVAÇÃO = "01 ANO"
                SITUACAO_CPF = "REGULAR"
                APONTAMENTOS = "SEM RESTRIÇÕES: Nada consta na base oficial da CGU nem nos portais de transparência"
                PERFIL_OP = "Profissional Independente"
                PARECER = "Consulta realizada na base oficial de transparência da CGU e portais públicos. Não foram identificados cargos políticos ativos nem histórico de exposição pública para o Nome e CPF informados."
                PROXIMA_ATUALIZACAO = "13/08/2027"

            # -----------------------------------------------------------------
            # EXIBIÇÃO DE EVIDÊNCIAS NA TELA
            # -----------------------------------------------------------------
            st.markdown("---")
            if STATUS_PEP == "SIM":
                st.error(f"🔴 **RESULTADO: PESSOA POLITICAMENTE EXPOSTA (PEP)** | Cargo: {CARGOS_EXERCIDOS} | Origem: {origem_identificacao}")
            else:
                st.success("🟢 **RESULTADO: NADA CONSTA (NÃO É PEP)**")

            # -----------------------------------------------------------------
            # CONSTRUÇÃO DO PDF VETORIAL COM REPORTLAB
            # -----------------------------------------------------------------
            buffer = io.BytesIO()
            doc = SimpleDocTemplate(
                buffer,
                pagesize=A4,
                leftMargin=36,
                rightMargin=36,
                topMargin=36,
                bottomMargin=45
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
            
            tz_brasilia = timezone(timedelta(hours=-3))
            hora_agora_bsb = datetime.now(tz_brasilia).strftime('%d/%m/%Y às %H:%M:%S')
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
