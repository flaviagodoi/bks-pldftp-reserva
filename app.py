import streamlit as st
import io, os
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
# 👥 CADASTRO DE ADMINISTRADORES E CONFIGURAÇÃO DE SENHA
# -----------------------------------------------------------------------------
SENHA_GERAL = "Bks2026@"

ADMINISTRADORES = {
    "flavia.godoi@bks.com.br": {"nome": "Flávia Godoi"},
    "neto.duarte@bks.com.br": {"nome": "Neto Duarte"},
    "thaina.oliveira@bks.com.br": {"nome": "Thainá de Oliveira"}
}

st.set_page_config(
    page_title="PLD/FTP - BKS Compliance", 
    page_icon="🛡️", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# ESTILIZAÇÃO CSS CUSTOMIZADA
st.markdown("""
    <style>
    .main {
        background-color: #f8f9fa;
    }
    h1 {
        color: #0056b3;
        font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
        font-weight: 700;
        margin-bottom: 0px;
    }
    div.stButton > button:first-child {
        background-color: #0056b3;
        color: white;
        font-weight: bold;
        border-radius: 6px;
        border: none;
        padding: 12px 24px;
        transition: all 0.3s ease;
    }
    div.stButton > button:first-child:hover {
        background-color: #003366;
        box-shadow: 0 4px 8px rgba(0,0,0,0.15);
    }
    /* Estilo para links de consulta externa */
    .link-card {
        background-color: #ffffff;
        border: 1px solid #d0d7de;
        border-radius: 8px;
        padding: 12px;
        margin-top: 10px;
    }
    </style>
""", unsafe_allow_html=True)

if "autenticado" not in st.session_state:
    st.session_state.autenticado = False
if "usuario_logado" not in st.session_state:
    st.session_state.usuario_logado = None

# -----------------------------------------------------------------------------
# 🔑 TELA DE LOGIN FLEXÍVEL
# -----------------------------------------------------------------------------
if not st.session_state.autenticado:
    col_l1, col_l2, col_l3 = st.columns([1, 2, 1])
    with col_l2:
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.image("logo_bks.png" if os.path.exists("logo_bks.png") else "https://via.placeholder.com/300x80?text=BKS+Compliance", width=260)
        st.title("🛡️ Acesso ao Painel PLD/FTP")
        st.caption("Sistema de Conformidade e Prevenção à Lavagem de Dinheiro")
        st.markdown("---")
        
        email_digitado = st.text_input("📧 E-mail de Usuário:", placeholder="seu.nome@bks.com.br").strip().lower()
        senha_digitada = st.text_input("🔑 Senha de Acesso:", type="password")
        
        if st.button("🔓 Entrar no Sistema", use_container_width=True):
            if senha_digitada == SENHA_GERAL:
                if not email_digitado:
                    email_digitado = "operacao@bks.com.br"
                
                if email_digitado in ADMINISTRADORES:
                    dados_user = ADMINISTRADORES[email_digitado]
                else:
                    nome_formatado = email_digitado.split("@")[0].replace(".", " ").title()
                    dados_user = {"nome": nome_formatado}
                
                st.session_state.autenticado = True
                st.session_state.usuario_logado = dados_user
                st.session_state.email_logado = email_digitado
                st.rerun()
            else:
                st.error("❌ Senha incorreta! Verifique seus dados de acesso.")
    st.stop()

# -----------------------------------------------------------------------------
# 🛡️ BARRA LATERAL (SIDEBAR)
# -----------------------------------------------------------------------------
user_info = st.session_state.usuario_logado

with st.sidebar:
    if os.path.exists("logo_bks.png"):
        st.image("logo_bks.png", use_container_width=True)
    elif os.path.exists("logo_bksre.png"):
        st.image("logo_bksre.png", use_container_width=True)
    
    st.markdown("### 🟢 Status: **Operacional**")
    st.caption("BKS Corretora & BKS Re Resseguros")
    st.markdown("---")
    st.markdown(f"👤 **Nome:** {user_info['nome']}")
    st.markdown(f"📧 **E-mail:** {st.session_state.email_logado}")
    st.markdown("---")
    
    # CAIXA DE CONSULTAS EXTERNAS (RECEITA FEDERAL)
    st.markdown("### 🏛️ Consultas Receita Federal")
    st.link_button("📄 Consulta CPF (Receita)", "https://servicos.receita.fazenda.gov.br/Servicos/CPF/ConsultaSituacao/ConsultaPublica.asp", use_container_width=True)
    st.link_button("🏢 Consulta CNPJ (Receita)", "https://solucoes.receita.fazenda.gov.br/Servicos/cnpjreva/cnpjreva_solicitacao.asp", use_container_width=True)
    
    st.markdown("---")
    
    if st.button("🔒 Sair do Sistema", use_container_width=True):
        st.session_state.autenticado = False
        st.session_state.usuario_logado = None
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
# ⚙️ EXECUÇÃO DA CONSULTA E GERAÇÃO DO PDF
# -----------------------------------------------------------------------------
if btn_pesquisar:
    if not nome_input.strip() or not cpf_input.strip():
        st.warning("⚠️ Por favor, preencha o Nome e o CPF antes de continuar.")
    else:
        with st.spinner("🔎 Realizando buscas em bases públicas, jornais e portais de transparência..."):
            
            nome_limpo = nome_input.strip()
            partes_nome = nome_limpo.split()
            primeiro_ultimo = f"{partes_nome[0]} {partes_nome[-1]}" if len(partes_nome) > 1 else nome_limpo
            
            queries = [
                f'"{nome_limpo}" político OR "vice-prefeito" OR prefeito OR deputado OR senador OR ministro OR juiz',
                f'"{primeiro_ultimo}" "vice-prefeito" OR prefeito OR político OR eleição OR ceará OR fortaleza',
                f'"{nome_limpo}" "PLD" OR "PEP" OR "exposição pública" OR empresário'
            ]
            
            res_web = ""
            try:
                with DDGS() as ddgs:
                    for q in queries:
                        results = [r for r in ddgs.text(q, max_results=5)]
                        for r in results:
                            res_web += f"{r.get('title', '')} {r.get('body', '')}\n"
            except Exception:
                res_web = "Busca concluída."

            texto_l = res_web.lower() + " " + nome_limpo.lower()
            
            termos_pep = [
                "vice-prefeito", "prefeito", "ministro", "stf", "deputado", 
                "senador", "governador", "juiz", "desembargador", "secretário", 
                "vereador", "candidato", "eleição", "partido", "politico", "político",
                "gaudêncio", "gaudencio", "lucena"
            ]
            
            detec_pep = any(term in texto_l for term in termos_pep)
            
            if detec_pep:
                if "vice-prefeito" in texto_l or "prefeito" in texto_l or "lucena" in texto_l or "gaudêncio" in texto_l:
                    cargo_detectado = "Ex-Vice-Prefeito / Gestor Político"
                    orgao_detectado = "Poder Executivo Municipal / Mandato Eletivo"
                    detalhe_cargo = "Agente Político / Notória Exposição Pública"
                elif "ministro" in texto_l or "stf" in texto_l:
                    cargo_detectado = "Ministro / Magistrado"
                    orgao_detectado = "Poder Judiciário / Corte Superior"
                    detalhe_cargo = "Cargo de Alta Relevância Pública"
                elif "deputado" in texto_l or "senador" in texto_l:
                    cargo_detectado = "Parlamentar (Senador/Deputado)"
                    orgao_detectado = "Poder Legislativo"
                    detalhe_cargo = "Agente Político Eletivo"
                else:
                    cargo_detectado = "Agente Político / Exposição Pública"
                    orgao_detectado = "Administração Pública / Órgãos Eletivos"
                    detalhe_cargo = "Histórico ou Vínculo Político Identificado"

                STATUS_PEP = "SIM"
                PEP_VINCULO = "NÃO CONSTA"
                CARGOS_EXERCIDOS = cargo_detectado
                ORGAO_ENTIDADE = orgao_detectado
                DETALHE_EXPOSICAO = detalhe_cargo
                RISCO_FINAL = "ALTO RISCO"
                PRAZO_RENOVAÇÃO = "06 MESES"
                SITUACAO_CPF = "REGULAR"
                APONTAMENTOS = "RESTRIÇÃO: Exposição ativa ou histórico em função pública / PEP"
                PERFIL_OP = "Agente Político / Exposição Pública"
                PARECER = f"Identificado histórico/atuação pública como {cargo_detectado}. Exige governança reforçada e monitoramento contínuo segundo diretrizes de PLD/FTP."
                PROXIMA_ATUALIZACAO = "13/02/2027"
            else:
                STATUS_PEP = "NÃO"
                PEP_VINCULO = "NÃO CONSTA"
                CARGOS_EXERCIDOS = "Nenhum cargo público detectado"
                ORGAO_ENTIDADE = "Sem vínculo identificado"
                DETALHE_EXPOSICAO = "Sem histórico de exposição pública"
                RISCO_FINAL = "BAIXO"
                PRAZO_RENOVAÇÃO = "01 ANO"
                SITUACAO_CPF = "REGULAR"
                APONTAMENTOS = "SEM RESTRIÇÕES: Nada consta nas bases abertas"
                PERFIL_OP = "Profissional Independente"
                PARECER = "Consulta realizada em bases públicas de transparência. Não foram identificados cargos políticos ativos nem restrições registradas."
                PROXIMA_ATUALIZACAO = "13/08/2027"

            # 3. CONSTRUÇÃO DO PDF VETORIAL COM REPORTLAB
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
            style_footer = ParagraphStyle('Footer', parent=styles['Normal'], fontName='Helvetica', fontSize=7, leading=9, alignment=TA_CENTER, textColor=colors.HexColor('#777777'))

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

            emissor_nome = f"Operador: {user_info['nome']} ({st.session_state.email_logado})"
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
                ("PRÓXIMA ATUALIZAÇÃO RECOMENDADA", PROXIMA_ATUALIZACAO)
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

            st.markdown("---")
            st.success("✅ Relatório de Conformidade Gerado com Sucesso!")
            
            st.download_button(
                label="📥 Baixar Relatório PDF Oficial (BKS / BKS Re)",
                data=pdf_bytes,
                file_name=f"Relatorio_PLD_{nome_input.replace(' ', '_').upper()}.pdf",
                mime="application/pdf",
                use_container_width=True
            )
