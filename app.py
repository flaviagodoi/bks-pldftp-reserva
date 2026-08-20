import streamlit as st
import io, os, re, unicodedata, requests, csv
from datetime import datetime, timezone, timedelta
from PIL import Image as PILImage
from duckduckgo_search import DDGS
from sqlalchemy import create_engine, text

# ReportLab - Gerador Vetorial Profissional de PDF
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

# -----------------------------------------------------------------------------
# 🗄️ CONEXÃO NATIVA E PERMANENTE COM BANCO SUPABASE (POSTGRESQL)
# -----------------------------------------------------------------------------
def obter_conexao_banco():
    """Retorna a engine de conexão do SQLAlchemy para o Supabase."""
    if "DATABASE_URL" in st.secrets:
        db_url = st.secrets["DATABASE_URL"]
        # Ajuste de prefixo do SQLAlchemy para Postgres
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
        return create_engine(db_url, pool_pre_ping=True)
    return None

def inicializar_banco_supabase():
    """Cria a tabela no Supabase automaticamente se ela ainda não existir."""
    engine = obter_conexao_banco()
    if engine:
        try:
            with engine.connect() as conn:
                conn.execute(text('''
                    CREATE TABLE IF NOT EXISTS vencimentos_pld (
                        nome TEXT,
                        cpf TEXT,
                        cpf_mascarado TEXT,
                        cpf_key TEXT PRIMARY KEY,
                        operador TEXT,
                        data_emissao TEXT,
                        status_pep TEXT,
                        data_vencimento TEXT,
                        data_vencimento_iso TEXT
                    );
                '''))
                conn.commit()
        except Exception:
            pass

inicializar_banco_supabase()

# -----------------------------------------------------------------------------
# 🔐 CONTROLE DE ACESSO, HIERARQUIA DE CARGOS E USUÁRIOS
# -----------------------------------------------------------------------------
CARGOS_NATIVOS = {
    "flavia.godoi@bks.com.br": "Administrador/Programador",
    "marcio.akama@bks.com.br": "Diretoria",
    "leiko.akama@bks.com.br": "Diretoria",
    "neto.duarte@bks.com.br": "Gerente",
    "thaina.oliveira@bks.com.br": "Administrador"
}

USUARIOS_PADRAO_NATIVOS = [
    "ariana.reis@bks.com.br",
    "danielle.almeida@bks.com.br",
    "carlos.alberto@bks.com.br",
    "sheila.giopato@bks.com.br",
    "giovanna.oliveira@bks.com.br",
    "yuji.akama@bksre.com.br",
    "seguros@bks.com.br"
]

ARQUIVO_USUARIOS = "usuarios_aprovados.csv"

def carregar_usuarios():
    """Carrega a lista de usuários mantendo a hierarquia corporativa."""
    usuarios = {}
    
    if os.path.exists(ARQUIVO_USUARIOS):
        try:
            with open(ARQUIVO_USUARIOS, mode='r', encoding='utf-8') as f:
                reader = csv.reader(f, delimiter=';')
                for row in reader:
                    if row and len(row) >= 1 and row[0].strip():
                        email = row[0].strip().lower()
                        cargo = row[1].strip() if len(row) >= 2 else "Operador"
                        usuarios[email] = cargo
        except Exception:
            pass

    for usr in USUARIOS_PADRAO_NATIVOS:
        if usr.lower() not in usuarios:
            usuarios[usr.lower()] = "Operador"

    for email_adm, cargo_adm in CARGOS_NATIVOS.items():
        usuarios[email_adm.lower()] = cargo_adm

    return usuarios

def salvar_usuarios_csv(dict_usuarios):
    """Grava os usuários e papéis no arquivo local."""
    try:
        with open(ARQUIVO_USUARIOS, mode='w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f, delimiter=';')
            for email, cargo in dict_usuarios.items():
                writer.writerow([email, cargo])
    except Exception as e:
        st.error(f"Erro ao salvar lista de usuários: {e}")

def adicionar_novo_usuario(email_input, cargo_escolhido):
    """Adiciona um novo e-mail com o cargo definido."""
    email_clean = email_input.strip().lower()
    if not email_clean:
        return False, "O e-mail não pode estar em branco."
    
    dict_atual = carregar_usuarios()
    if email_clean in dict_atual:
        return False, "Este e-mail já está cadastrado!"

    dict_atual[email_clean] = cargo_escolhido
    salvar_usuarios_csv(dict_atual)
    return True, f"Usuário {email_clean} ({cargo_escolhido}) cadastrado com sucesso!"

def remover_usuario(email_remover):
    """Remove um usuário cadastrado."""
    email_clean = email_remover.strip().lower()
    dict_atual = carregar_usuarios()
    
    if email_clean in [a.lower() for a in CARGOS_NATIVOS.keys()]:
        return False, "E-mail protegido contra exclusão."

    if email_clean in dict_atual:
        del dict_atual[email_clean]
        salvar_usuarios_csv(dict_atual)
        return True, f"Acesso do e-mail {email_clean} revogado com sucesso."
    return False, "Usuário não localizado."

def verificar_email_autorizado(email: str) -> bool:
    """Verifica se o e-mail possui permissão de login no sistema."""
    if not email:
        return False
    email_clean = email.strip().lower()
    dict_usuarios = carregar_usuarios()
    return email_clean in dict_usuarios or email_clean.endswith("@bks.com.br") or email_clean.endswith("@bksre.com.br")

def eh_administrador(email: str) -> bool:
    """Retorna True se o e-mail logado tiver privilégios administrativos."""
    if not email:
        return False
    email_clean = email.strip().lower()
    dict_usuarios = carregar_usuarios()
    cargo = dict_usuarios.get(email_clean, "Operador")
    return cargo in ["Administrador/Programador", "Diretoria", "Gerente", "Administrador"] or email_clean in [a.lower() for a in CARGOS_NATIVOS.keys()]

def obter_cargo_usuario(email: str) -> str:
    """Retorna o título do cargo do e-mail informado."""
    if not email:
        return "Operador"
    email_clean = email.strip().lower()
    dict_usuarios = carregar_usuarios()
    return dict_usuarios.get(email_clean, "Operador")

# -----------------------------------------------------------------------------
# 🛠️ FUNÇÕES DE MÁSCARA, VALIDAÇÃO E REGISTRO NO SUPABASE
# -----------------------------------------------------------------------------
def formatar_cpf_estetico(cpf_raw: str) -> str:
    """Aplica a máscara estética 000.000.000-00 mantendo os zeros à esquerda."""
    nums = re.sub(r'\D', '', str(cpf_raw))
    if len(nums) == 11:
        return f"{nums[:3]}.{nums[3:6]}.{nums[6:9]}-{nums[9:]}"
    return str(cpf_raw).strip()

def mascarar_cpf(cpf_raw: str) -> str:
    """Oculta o miolo do CPF no padrão LGPD (ex: 123.***.***-89)."""
    nums = re.sub(r'\D', '', str(cpf_raw))
    if len(nums) == 11:
        return f"{nums[:3]}.***.***-{nums[9:]}"
    return "***.***.***-**"

def normalizar_texto(txt):
    """Remove acentos, caracteres especiais e converte para caixa baixa."""
    if not txt:
        return ""
    nfkd = unicodedata.normalize('NFD', str(txt))
    sem_acento = "".join([c for c in nfkd if not unicodedata.combining(c)])
    limpo = re.sub(r'[^a-zA-Z0-9\s]', ' ', sem_acento).lower()
    return " ".join(limpo.split())

def validar_cpf(cpf: str) -> bool:
    """Valida os dígitos verificadores do CPF (Módulo 11)."""
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

def registrar_vencimento(nome, cpf_raw, email_operador, status_pep, data_emissao_dt, data_vencimento_str):
    """Grava o registro de forma PERMANENTE no banco de dados do Supabase."""
    cpf_limpo_key = re.sub(r'\D', '', str(cpf_raw))
    cpf_formatado = formatar_cpf_estetico(cpf_raw)
    cpf_mascarado = mascarar_cpf(cpf_raw)
    
    try:
        dt_venc = datetime.strptime(data_vencimento_str, "%d/%m/%Y").strftime("%Y-%m-%d")
    except Exception:
        dt_venc = data_vencimento_str

    engine = obter_conexao_banco()
    if engine:
        try:
            with engine.connect() as conn:
                query = text('''
                    INSERT INTO vencimentos_pld (nome, cpf, cpf_mascarado, cpf_key, operador, data_emissao, status_pep, data_vencimento, data_vencimento_iso)
                    VALUES (:nome, :cpf, :cpf_mascarado, :cpf_key, :operador, :data_emissao, :status_pep, :data_vencimento, :data_vencimento_iso)
                    ON CONFLICT (cpf_key) DO UPDATE SET
                        nome = EXCLUDED.nome,
                        cpf = EXCLUDED.cpf,
                        cpf_mascarado = EXCLUDED.cpf_mascarado,
                        operador = EXCLUDED.operador,
                        data_emissao = EXCLUDED.data_emissao,
                        status_pep = EXCLUDED.status_pep,
                        data_vencimento = EXCLUDED.data_vencimento,
                        data_vencimento_iso = EXCLUDED.data_vencimento_iso;
                ''')
                conn.execute(query, {
                    "nome": nome.upper().strip(),
                    "cpf": cpf_formatado,
                    "cpf_mascarado": cpf_mascarado,
                    "cpf_key": cpf_limpo_key,
                    "operador": email_operador,
                    "data_emissao": data_emissao_dt.strftime("%d/%m/%Y %H:%M"),
                    "status_pep": status_pep,
                    "data_vencimento": data_vencimento_str,
                    "data_vencimento_iso": dt_venc
                })
                conn.commit()
        except Exception as e:
            st.error(f"Erro ao salvar no Supabase: {e}")

def carregar_vencimentos():
    """Lê a lista completa de relatórios diretamente da nuvem do Supabase."""
    registros = []
    engine = obter_conexao_banco()
    if engine:
        try:
            with engine.connect() as conn:
                res = conn.execute(text("SELECT nome, cpf, cpf_mascarado, cpf_key, operador, data_emissao, status_pep, data_vencimento, data_vencimento_iso FROM vencimentos_pld ORDER BY data_vencimento_iso ASC;"))
                for r in res:
                    registros.append({
                        "Nome": r[0],
                        "CPF": r[1],
                        "CPF_Mascarado": r[2],
                        "CPF_Key": r[3],
                        "Operador": r[4],
                        "Data_Emissao": r[5],
                        "Status_PEP": r[6],
                        "Data_Vencimento": r[7],
                        "Data_Vencimento_ISO": r[8]
                    })
        except Exception:
            pass
    return registros

# -----------------------------------------------------------------------------
# 🛠️ FUNÇÕES DE BUSCA (CGU + WIKIPÉDIA + WEB)
# -----------------------------------------------------------------------------
def identificar_arquivo_pep():
    """Localiza o arquivo da planilha de PEPs no diretório local."""
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
    """Busca de alta precisão na planilha da CGU."""
    caminho_final = identificar_arquivo_pep()
    if not caminho_final:
        return None

    nome_norm = normalizar_texto(nome_input)
    if not nome_norm or len(nome_norm.split()) < 2:
        return None

    cpf_numeros = re.sub(r'\D', '', str(cpf_input))
    miolo_cpf_input = cpf_numeros[3:9] if len(cpf_numeros) == 11 else ""

    try:
        with open(caminho_final, mode='r', encoding='utf-8', errors='ignore') as f:
            primeira_linha = f.readline()
            sep = ';' if ';' in primeira_linha else (',' if ',' in primeira_linha else '\t')
            f.seek(0)

            reader = csv.DictReader(f, delimiter=sep)
            for row in reader:
                nome_pep_row = (row.get('Nome_PEP') or row.get('NOME_PEP') or 
                                row.get('Nome') or row.get('NOME') or row.get('Nome_Pessoa') or "")
                
                nome_pep_norm = normalizar_texto(nome_pep_row)

                if nome_norm == nome_pep_norm:
                    cpf_row = (row.get('CPF') or row.get('Cpf') or row.get('CPF_PEP') or 
                               row.get('CPF_PESSOA') or row.get('Cpf_Pessoa') or "")
                    
                    cpf_row_numeros = re.sub(r'\D', '', cpf_row)

                    if miolo_cpf_input and len(cpf_row_numeros) >= 6:
                        if miolo_cpf_input not in cpf_row_numeros:
                            continue

                    cargo = (row.get('Descrição_Função') or row.get('DESCRICAO_FUNCAO') or 
                             row.get('DS_FUNCAO') or row.get('Função') or row.get('Cargo') or "Agente Político / Função Pública")
                    
                    orgao = (row.get('Nome_Órgão') or row.get('NOME_ORGAO') or 
                             row.get('Órgão') or row.get('Orgao') or row.get('ORGAO_LOTACAO') or "Administração Pública (CGU)")

                    return {
                        "cargo": str(cargo).strip(),
                        "orgao": str(orgao).strip(),
                        "detalhe": f"Registro Oficial na Base da CGU ({caminho_final})"
                    }
    except Exception:
        pass

    return None

def buscar_wikipedia(nome):
    """Busca resumo do pesquisado na Wikipédia em Português."""
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
    """Analisa vinculação a cargo público no raio de 250 caracteres."""
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
    div.stButton > button:first-child { background-color: #0056b3; color: white; font-weight: bold; border-radius: 6px; border: none; padding: 10px 20px; transition: all 0.3s ease; }
    div.stButton > button:first-child:hover { background-color: #003366; box-shadow: 0 4px 8px rgba(0,0,0,0.15); }
    
    a.btn-receita-azul {
        display: block;
        width: 100%;
        background-color: #0056b3;
        color: white !important;
        text-align: center;
        font-weight: bold;
        padding: 12px 20px;
        border-radius: 6px;
        text-decoration: none;
        margin-top: 10px;
        transition: all 0.3s ease;
    }
    a.btn-receita-azul:hover {
        background-color: #003366;
        box-shadow: 0 4px 8px rgba(0,0,0,0.2);
    }
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
                if verificar_email_autorizado(email_digitado):
                    st.session_state.autenticado = True
                    st.session_state.email_logado = email_digitado
                    st.rerun()
                else:
                    st.error("⚠️ **Acesso Negado:** O e-mail informado não possui permissão de acesso. Contate um administrador de compliance.")
            else:
                st.error("❌ Senha incorreta! Verifique seus dados de acesso.")
    st.stop()

# -----------------------------------------------------------------------------
# 🛡️ BARRA LATERAL (SIDEBAR) & NAVEGAÇÃO
# -----------------------------------------------------------------------------
eh_admin = eh_administrador(st.session_state.email_logado)
cargo_usuario_logado = obter_cargo_usuario(st.session_state.email_logado)

with st.sidebar:
    col_logo1, col_logo2 = st.columns(2)
    with col_logo1:
        if os.path.exists("logo_bks.png"):
            st.image("logo_bks.png", use_container_width=True)
        else:
            st.caption("BKS Corretora")
    with col_logo2:
        if os.path.exists("logo_bksre.png"):
            st.image("logo_bksre.png", use_container_width=True)
        else:
            st.caption("BKS Re Resseguros")
            
    st.markdown("### 🟢 Status: **Operacional**")
    st.caption("BKS Corretora & BKS Re Resseguros")
    st.markdown("---")
    
    st.markdown(f"📧 **Operador:** {st.session_state.email_logado}\n\n*(⭐ {cargo_usuario_logado})*")
        
    st.markdown("---")
    
    opcoes_menu = [
        "🏛️ Consultas Receita Federal (PF/PJ)",
        "🔍 Consulta PLD/FTP", 
        "📊 Gestão de Vencimentos", 
        "⚙️ Gerenciador de Usuários"
    ]

    opcao_menu = st.radio(
        "📌 Menu de Navegação:",
        opcoes_menu,
        index=0
    )
    
    st.markdown("---")
    
    arquivo_encontrado = identificar_arquivo_pep()
    if arquivo_encontrado:
        data_arquivo = datetime(2026, 8, 14)
        dias_desde_atualizacao = (datetime.now() - data_arquivo).days

        if dias_desde_atualizacao > 30:
            st.warning(f"⚠️ **Base PEP Local:** Atualização Necessária!\n(Inclusão de {data_arquivo.strftime('%d/%m/%Y')} - há {dias_desde_atualizacao} dias)")
            st.caption("💡 *Aviso: Favor solicitar ao Administrador a atualização da base do Portal da Transparência (CGU).*")
        else:
            st.success("📁 **Base PEP Local:** Carregada e Ativa")
            st.caption(f"🗓️ *Inclusão da base: {data_arquivo.strftime('%d/%m/%Y')}*")
            st.caption("🏛️ *Fonte: Portal da Transparência - Controladoria Geral da União*")
    else:
        st.info("🌐 **Base PEP Local:** Não enc. (Modo Web Ativo)")

    st.markdown("---")
    
    if st.button("🔒 Sair do Sistema", use_container_width=True):
        st.session_state.autenticado = False
        st.session_state.email_logado = None
        st.session_state.renovar_nome = ""
        st.session_state.renovar_cpf = ""
        st.rerun()

# =============================================================================
# 🏛️ TELA 1: CONSULTAS RECEITA FEDERAL (PF / PJ)
# =============================================================================
if opcao_menu == "🏛️ Consultas Receita Federal (PF/PJ)":
    st.title("🏛️ Consultas Oficiais na Receita Federal")
    st.caption("Acesso direto aos portais governamentais para emissão de Comprovante de Situação Cadastral de CPF e CNPJ.")
    st.markdown("<br>", unsafe_allow_html=True)

    col_rf1, col_rf2 = st.columns(2)
    
    with col_rf1:
        st.markdown("### 📄 Pessoa Física (CPF)")
        st.write("Acesse a página oficial da Receita Federal para emitir e validar o comprovante de situação cadastral do CPF.")
        st.markdown('<a href="https://servicos.receita.fazenda.gov.br/Servicos/CPF/ConsultaSituacao/ConsultaPublica.asp" target="_blank" class="btn-receita-azul">👉 Acessar Consulta CPF (Receita Federal)</a>', unsafe_allow_html=True)

    with col_rf2:
        st.markdown("### 🏢 Pessoa Jurídica (CNPJ)")
        st.write("Acesse a página oficial da Receita Federal para emitir o Cartão CNPJ e verificar a situação cadastral da empresa.")
        st.markdown('<a href="https://solucoes.receita.fazenda.gov.br/Servicos/cnpjreva/cnpjreva_solicitacao.asp" target="_blank" class="btn-receita-azul">👉 Acessar Consulta CNPJ (Receita Federal)</a>', unsafe_allow_html=True)

    st.markdown("<br><br>---", unsafe_allow_html=True)
    st.info("💡 **Dica de Governança:** É recomendado anexar a Consulta de Situação Cadastral emitida nestes links ao laudo final de PLD/FTP para documentação de auditoria.")

# =============================================================================
# 📌 TELA 2: CONSULTA PLD/FTP
# =============================================================================
elif opcao_menu == "🔍 Consulta PLD/FTP":
    st.title("🛡️ Painel Oficial de Consulta PLD/FTP")
    st.caption("Pesquisa automatizada em portais de transparência e bases públicas para enquadramento regulatório.")
    st.markdown("<br>", unsafe_allow_html=True)

    val_nome_def = st.session_state.renovar_nome if st.session_state.renovar_nome else ""
    val_cpf_def = formatar_cpf_estetico(st.session_state.renovar_cpf) if st.session_state.renovar_cpf else ""

    with st.container():
        st.markdown("### 📋 Dados do Pesquisado")
        col1, col2 = st.columns(2)
        with col1:
            nome_input = st.text_input("👉 Nome Completo do Pesquisado", value=val_nome_def, placeholder="Ex: João da Silva")
        with col2:
            cpf_input = st.text_input("👉 CPF do Pesquisado (Números ou Formatado)", value=val_cpf_def, placeholder="000.000.000-00")

        st.markdown("<br>", unsafe_allow_html=True)
        btn_pesquisar = st.button("🔎 Iniciar Consulta e Gerar Relatório PDF", type="primary", use_container_width=True)

    if btn_pesquisar or (st.session_state.renovar_nome and st.session_state.renovar_cpf):
        st.session_state.renovar_nome = ""
        st.session_state.renovar_cpf = ""
        
        cpf_valido_bool = validar_cpf(cpf_input)
        cpf_formatado_input = formatar_cpf_estetico(cpf_input)
        
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

                # REGISTRA NO NUVEM SUPABASE PERMANENTE
                registrar_vencimento(
                    nome=nome_input,
                    cpf_raw=cpf_input,
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
                    ("CPF", cpf_formatado_input),
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
# 📊 TELA 3: GESTÃO DE VENCIMENTOS DOS RELATÓRIOS
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

            cpf_completo = reg.get("CPF_Key", reg.get("CPF", ""))
            cpf_mascarado = reg.get("CPF_Mascarado", mascarar_cpf(cpf_completo))

            dados_processados.append({
                "Nome Completo": reg.get("Nome", ""),
                "CPF_Exibicao": cpf_mascarado,
                "CPF_Real": cpf_completo,
                "CPF_Excel": f'="{cpf_mascarado}"',
                "Status PEP": reg.get("Status_PEP", ""),
                "Data de Emissão": reg.get("Data_Emissao", ""),
                "Data de Vencimento": reg.get("Data_Vencimento", ""),
                "Status do Prazo": status_alerta,
                "Operador": reg.get("Operador", "")
            })

        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        col_m1.metric("Total de Relatórios", len(registros))
        col_m2.metric("🟢 Dentro do Prazo", validos)
        col_m3.metric("🟡 Vencem em até 30 dias", a_vencer_breve)
        col_m4.metric("🔴 Vencidos / Expirados", vencidos)

        st.markdown("---")
        st.subheader("🔍 Filtros de Busca")

        col_f1, col_f2 = st.columns([1, 2])
        with col_f1:
            filtro_status = st.selectbox(
                "Filtrar por Status do Prazo:",
                ["Todos", "🔴 Apenas Vencidos", "🟡 Vencem em breve", "🟢 Apenas Válidos"]
            )
        with col_f2:
            termo_busca = st.text_input("Buscar por Nome ou CPF:", placeholder="Digite o nome ou CPF...")

        dados_filtrados = []
        for item in dados_processados:
            if filtro_status == "🔴 Apenas Vencidos" and "🔴" not in item["Status do Prazo"]:
                continue
            elif filtro_status == "🟡 Vencem em breve" and "🟡" not in item["Status do Prazo"]:
                continue
            elif filtro_status == "🟢 Apenas Válidos" and "🟢" not in item["Status do Prazo"]:
                continue

            if termo_busca:
                tb_norm = normalizar_texto(termo_busca)
                nome_norm = normalizar_texto(item["Nome Completo"])
                cpf_limpo = re.sub(r'\D', '', item["CPF_Real"])
                tb_limpo = re.sub(r'\D', '', termo_busca)
                if tb_norm not in nome_norm and (tb_limpo == "" or tb_limpo not in cpf_limpo):
                    continue

            dados_filtrados.append(item)

        st.markdown("<br>", unsafe_allow_html=True)
        st.subheader("📋 Relatórios Cadastrados")

        if not dados_filtrados:
            st.warning("Nenhum registro localizado com os filtros selecionados.")
        else:
            col_h1, col_h2, col_h3, col_h4, col_h5, col_h6, col_h7 = st.columns([2.5, 1.3, 1, 1.5, 1.2, 1.2, 1])
            with col_h1:
                st.markdown("**👤 Nome Completo**")
            with col_h2:
                st.markdown("**📄 CPF (LGPD)**")
            with col_h3:
                st.markdown("**🛡️ Status PEP**")
            with col_h4:
                st.markdown("**📅 Data Emissão**")
            with col_h5:
                st.markdown("**⏰ Data Vencimento**")
            with col_h6:
                st.markdown("**📌 Status Prazo**")
            with col_h7:
                st.markdown("**⚡ Ação**")
            st.markdown("<hr style='margin-top:2px; margin-bottom:8px;'>", unsafe_allow_html=True)

            for idx, item in enumerate(dados_filtrados):
                c_n, c_c, c_p, c_e, c_v, c_s, c_b = st.columns([2.5, 1.3, 1, 1.5, 1.2, 1.2, 1])
                
                with c_n:
                    st.write(f"**{item['Nome Completo']}**")
                with c_c:
                    st.write(item["CPF_Exibicao"])
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
                        st.session_state.renovar_cpf = item["CPF_Real"]
                        st.rerun()
                st.markdown("<hr style='margin-top:2px; margin-bottom:2px; border: 0.5px solid #e6e6e6;'>", unsafe_allow_html=True)

        if eh_admin:
            st.markdown("<br>", unsafe_allow_html=True)
            csv_buffer = io.StringIO()
            campos = ["Nome Completo", "CPF", "Status PEP", "Data de Emissão", "Data de Vencimento", "Status do Prazo", "Operador"]
            writer = csv.DictWriter(csv_buffer, fieldnames=campos, delimiter=';')
            writer.writeheader()
            
            dados_excel = []
            for d in (dados_filtrados if dados_filtrados else dados_processados):
                row_e = {
                    "Nome Completo": d["Nome Completo"],
                    "CPF": d["CPF_Excel"],
                    "Status PEP": d["Status PEP"],
                    "Data de Emissão": d["Data de Emissão"],
                    "Data de Vencimento": d["Data de Vencimento"],
                    "Status do Prazo": d["Status do Prazo"],
                    "Operador": d["Operador"]
                }
                dados_excel.append(row_e)

            writer.writerows(dados_excel)

            st.download_button(
                label="📥 Exportar Lista em Colunas (.CSV para Excel)",
                data=csv_buffer.getvalue().encode('utf-8-sig'),
                file_name=f"Controle_Vencimentos_PLD_BKS_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
                use_container_width=True
            )

# =============================================================================
# ⚙️ TELA 4: GERENCIADOR DE USUÁRIOS E PERMISSÕES
# =============================================================================
elif opcao_menu == "⚙️ Gerenciador de Usuários":
    st.title("⚙️ Gerenciador de Usuários Aprovados")
    st.caption("Painel de controle de acessos e permissões dos operadores.")
    st.markdown("<br>", unsafe_allow_html=True)

    if eh_admin:
        col_add1, col_add2, col_add3 = st.columns([2.5, 1.2, 1])
        with col_add1:
            novo_email_input = st.text_input("➕ Digite o e-mail para autorizar:", placeholder="novo.usuario@bks.com.br")
        with col_add2:
            perfil_input = st.selectbox("Cargo / Perfil:", ["Operador", "Administrador", "Gerente", "Diretoria"])
        with col_add3:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("✅ Autorizar", use_container_width=True):
                sucesso, msg = adicionar_novo_usuario(novo_email_input, perfil_input)
                if sucesso:
                    st.success(msg)
                    st.rerun()
                else:
                    st.warning(msg)
        st.markdown("---")

    st.subheader("📋 Lista de Usuários com Acesso Liberado")

    dict_usuarios = carregar_usuarios()

    if not dict_usuarios:
        st.info("Nenhum usuário cadastrado.")
    else:
        col_u_head1, col_u_head2, col_u_head3 = st.columns([3, 2, 1])
        with col_u_head1:
            st.markdown("**📧 E-mail Autorizado**")
        with col_u_head2:
            st.markdown("**Cargo / Perfil**")
        with col_u_head3:
            st.markdown("**Ação**")
        st.markdown("<hr style='margin-top:2px; margin-bottom:8px;'>", unsafe_allow_html=True)

        admins_nativos_lower = [a.lower() for a in CARGOS_NATIVOS.keys()]

        for idx, (usr_email, cargo_usr) in enumerate(sorted(dict_usuarios.items())):
            c_u1, c_u2, c_u3 = st.columns([3, 2, 1])
            with c_u1:
                st.write(f"**{usr_email}**")
            with c_u2:
                if cargo_usr == "Administrador/Programador":
                    st.write("⭐ Administrador/Programador")
                elif cargo_usr == "Diretoria":
                    st.write("🏛️ Diretoria")
                elif cargo_usr == "Gerente":
                    st.write("💼 Gerente")
                elif cargo_usr in ["Administrador", "admin"]:
                    st.write("🔑 Administrador")
                else:
                    st.write("👤 Operador")
            with c_u3:
                if eh_admin:
                    if usr_email in admins_nativos_lower or usr_email == st.session_state.email_logado.strip().lower():
                        st.caption("Protegido")
                    else:
                        if st.button("🗑️ Revogar", key=f"btn_del_usr_final_{usr_email}_{idx}"):
                            ok, msg_del = remover_usuario(usr_email)
                            if ok:
                                st.success(msg_del)
                                st.rerun()
                            else:
                                st.error(msg_del)
                else:
                    st.caption("🔒 Leitura")
            st.markdown("<hr style='margin-top:2px; margin-bottom:2px; border: 0.5px solid #e6e6e6;'>", unsafe_allow_html=True)
