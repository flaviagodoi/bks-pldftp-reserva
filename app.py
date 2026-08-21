import streamlit as st
import io, os, re, unicodedata, requests, csv, hashlib
from datetime import datetime, timezone, timedelta
from PIL import Image as PILImage
from duckduckgo_search import DDGS
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

# ReportLab - Gerador Vetorial Profissional de PDF
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

# -----------------------------------------------------------------------------
# 🔐 BLINDAGEM DE CHAVES E SENHAS VIA STREAMLIT SECRETS (SEM SENHA EXPOSTA NO CODE)
# -----------------------------------------------------------------------------
SENHA_GERAL = st.secrets.get("SENHA_GERAL", "")

# -----------------------------------------------------------------------------
# 🗄️ CONEXÃO NATIVA E PERMANENTE COM BANCO SUPABASE (POSTGRESQL)
# -----------------------------------------------------------------------------
def obter_conexao_banco():
    """Retorna a engine de conexão do SQLAlchemy para o Supabase sem prender pool."""
    if "DATABASE_URL" in st.secrets:
        db_url = st.secrets["DATABASE_URL"]
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
        return create_engine(db_url, poolclass=NullPool)
    return None

def inicializar_banco_supabase():
    """Cria as tabelas no Supabase automaticamente se ainda não existirem."""
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
                
                conn.execute(text('''
                    CREATE TABLE IF NOT EXISTS usuarios_auth (
                        email TEXT PRIMARY KEY,
                        senha_hash TEXT,
                        cargo TEXT,
                        criado_em TEXT
                    );
                '''))
                conn.commit()
        except Exception:
            pass

inicializar_banco_supabase()

# -----------------------------------------------------------------------------
# 🔐 GERENCIAMENTO DE SENHAS INDIVIDUAIS E USUÁRIOS (SUPABASE + HASH)
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

def gerar_hash_senha(senha: str) -> str:
    """Gera hash SHA-256 seguro para armazenamento de senhas."""
    if not senha:
        return ""
    return hashlib.sha256(senha.strip().encode('utf-8')).hexdigest()

def validar_complexidade_senha(senha: str):
    """Valida se a senha atende aos requisitos mínimos de complexidade corporativa."""
    s = senha.strip() if senha else ""
    if not s or len(s) < 8:
        return False, "A senha deve conter no mínimo 8 dígitos."
    if not re.search(r'[A-Z]', s):
        return False, "A senha deve conter pelo menos uma letra MAIÚSCULA."
    if not re.search(r'[a-z]', s):
        return False, "A senha deve conter pelo menos uma letra MINÚSCULA."
    if not re.search(r'[0-9]', s):
        return False, "A senha deve conter pelo menos um NÚMERO."
    if not re.search(r'[^a-zA-Z0-9]', s):
        return False, "A senha deve conter pelo menos um CARACTERE ESPECIAL (ex: @, #, $, !, %, *)."
    return True, ""

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
    except Exception:
        st.error("Erro interno ao atualizar permissões locais.")

def adicionar_novo_usuario(email_input, cargo_escolhido):
    """Adiciona um novo e-mail para autorização."""
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
        
        engine = obter_conexao_banco()
        if engine:
            try:
                with engine.connect() as conn:
                    conn.execute(text("DELETE FROM usuarios_auth WHERE LOWER(email) = LOWER(:email)"), {"email": email_clean})
                    conn.commit()
            except Exception:
                pass

        return True, f"Acesso do e-mail {email_clean} revogado com sucesso."
    return False, "Usuário não localizado."

def verificar_email_autorizado(email: str) -> bool:
    """Verifica se o e-mail possui permissão de login no sistema."""
    if not email:
        return False
    email_clean = email.strip().lower()
    dict_usuarios = carregar_usuarios()
    return email_clean in dict_usuarios or email_clean.endswith("@bks.com.br") or email_clean.endswith("@bksre.com.br")

def buscar_senha_usuario_banco(email: str):
    """Retorna o hash da senha e o cargo gravado no Supabase para o e-mail informado."""
    if not email:
        return None, None
    email_clean = email.strip().lower()
    engine = obter_conexao_banco()
    if engine:
        try:
            with engine.connect() as conn:
                res = conn.execute(text("SELECT senha_hash, cargo FROM usuarios_auth WHERE LOWER(email) = LOWER(:email)"), {"email": email_clean}).fetchone()
                if res:
                    return res[0], res[1]
        except Exception:
            pass
    return None, None

def cadastrar_senha_usuario_banco(email: str, senha_plana: str, cargo: str):
    """Grava a senha individual criptografada no Supabase eliminando duplicidades."""
    senha_h = gerar_hash_senha(senha_plana)
    criado_em = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    email_clean = email.strip().lower()
    engine = obter_conexao_banco()
    if engine:
        try:
            with engine.connect() as conn:
                conn.execute(text("DELETE FROM usuarios_auth WHERE LOWER(email) = LOWER(:email)"), {"email": email_clean})
                conn.execute(text('''
                    INSERT INTO usuarios_auth (email, senha_hash, cargo, criado_em)
                    VALUES (:email, :senha_hash, :cargo, :criado_em);
                '''), {"email": email_clean, "senha_hash": senha_h, "cargo": cargo, "criado_em": criado_em})
                conn.commit()
                return True
        except Exception:
            st.error("Erro ao salvar senha no banco seguro. Tente novamente.")
    return False

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
# 🛠️ MÁSCARAS, VALIDAÇÃO E MOTOR DE CROSS-VALIDATION NOME x CPF
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

def extrair_sufixo_familiar(palavras):
    sufixos = {"junior", "jr", "filho", "neto", "sobrinho"}
    if palavras and palavras[-1] in sufixos:
        suf = palavras[-1]
        return "junior" if suf == "jr" else suf
    return None

def nomes_sao_compativeis(nome1, nome2):
    """Compara se dois nomes se referem ao mesmo indivíduo com flexibilidade."""
    n1 = normalizar_texto(nome1)
    n2 = normalizar_texto(nome2)
    if not n1 or not n2:
        return True

    p1 = n1.split()
    p2 = n2.split()

    suf1 = extrair_sufixo_familiar(p1)
    suf2 = extrair_sufixo_familiar(p2)
    if suf1 != suf2:
        return False

    ignorar = {"de", "da", "do", "das", "dos", "e", "junior", "jr", "filho", "neto", "sobrinho"}
    w1 = [w for w in p1 if w not in ignorar]
    w2 = [w for w in p2 if w not in ignorar]

    if not w1 or not w2:
        return True

    if w1[0] != w2[0]:
        return False

    set1 = set(w1[1:]) if len(w1) > 1 else set(w1)
    set2 = set(w2[1:]) if len(w2) > 1 else set(w2)

    if not set1 or not set2:
        return True

    intersecao = set1.intersection(set2)
    return len(intersecao) >= 1

def validar_coerencia_nome_cpf(nome_input, cpf_input):
    """Motor de Cross-Validation Seguro para CPFs completos de 11 dígitos."""
    cpf_limpo = re.sub(r'\D', '', str(cpf_input))
    if len(cpf_limpo) != 11:
        return True, ""

    for chave_nat, dados_nat in BASE_PEP_NATIVA.items():
        cpf_conhecido = dados_nat.get("cpf_conhecido", "")
        if cpf_conhecido and cpf_limpo == cpf_conhecido:
            if not nomes_sao_compativeis(nome_input, chave_nat):
                return False, f"O CPF {formatar_cpf_estetico(cpf_input)} pertence a '{chave_nat}'. O nome digitado ({nome_input.upper()}) não corresponde a esta identidade."

    engine = obter_conexao_banco()
    if engine:
        try:
            with engine.connect() as conn:
                res = conn.execute(text("SELECT nome FROM vencimentos_pld WHERE cpf_key = :key"), {"key": cpf_limpo}).fetchone()
                if res and res[0]:
                    nome_banco = res[0]
                    if not nomes_sao_compativeis(nome_input, nome_banco):
                        return False, f"O CPF {formatar_cpf_estetico(cpf_input)} já possui laudo registrado no sistema para '{nome_banco}'. O nome informado ({nome_input.upper()}) é incompatível."
        except Exception:
            pass

    return True, ""

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
        except Exception:
            st.error("Falha ao registrar vencimento no banco seguro.")

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
# 🛠️ MECANISMO DE BUSCA AVANÇADO (CGU + WIKIPÉDIA + MAPEAMENTO NATIVO)
# -----------------------------------------------------------------------------
BASE_PEP_NATIVA = {
    "GAUDENCIO GONCALVES DE LUCENA": {
        "tipo": "DIRETO",
        "cpf_conhecido": "03429628334",
        "cargo": "Agente Político / Exposição Direta (Ex-Vice-Prefeito de Fortaleza / Suplente de Senador)",
        "orgao": "Administração Pública / Poder Executivo",
        "detalhe": "Histórico Mapeado de Notória Exposição e Função Pública Direta",
        "origem": "Base de Notória Exposição Pública e Função Pública"
    },
    "GAUDENCIO GONCALVES DE LUCENA JUNIOR": {
        "tipo": "FAMILIAR",
        "sufixo": "JUNIOR",
        "cpf_conhecido": "66632935320",
        "nome_parente": "Gaudêncio Gonçalves de Lucena",
        "cargo": "Vínculo Familiar de 1º Grau (Junior de Agente Político Exposto: Ex-Vice-Prefeito / Suplente)",
        "orgao": "Administração Pública (Vínculo Familiar de 1º Grau)",
        "detalhe": "Mapeamento Regulatório de Parentesco de 1º Grau com Agente Político Exposto (Gaudêncio Lucena)",
        "origem": "Mapeamento de Parentesco de 1º Grau em Fontes Públicas (Gaudêncio Lucena)"
    },
    "SHIGEAKI MARACAJA RAMOS": {
        "tipo": "FAMILIAR",
        "sufixo": "PARENTESCO",
        "cpf_conhecido": "02409509410",
        "nome_parente": "Estela Maracajá Ramos",
        "cargo": "Vínculo Familiar de 1º Grau (Filho de Agente Político Exposto: Vice-Prefeita de São João do Cariri)",
        "orgao": "Administração Pública / Poder Executivo Municipal",
        "detalhe": "Mapeamento Regulatório de Parentesco de 1º Grau com Agente Político Exposto (Estela Maracajá)",
        "origem": "Mapeamento de Parentesco de 1º Grau em Fontes Públicas (Estela Maracajá)"
    }
}

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
    """Busca estrita na planilha da CGU utilizando NOME COMPLETO EXATO e miolo do CPF."""
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

def buscar_web_robusta(nome):
    """Busca flexível e abrangente de dados públicos na Wikipédia e buscadores Web."""
    texto_compilado = ""
    nome_limpo = nome.strip()
    nome_norm = normalizar_texto(nome_limpo)
    partes = nome_norm.split()
    
    queries = [
        f'"{nome_limpo}"',
        f'"{nome_limpo}" politico OR prefeita OR prefeito OR vice OR mae OR pai'
    ]
    if len(partes) >= 3:
        queries.append(f'"{partes[0]} {partes[-1]}" politico OR prefeita OR vice')

    for q in queries:
        try:
            url_wiki = "https://pt.wikipedia.org/w/api.php"
            params_search = {
                "action": "query",
                "list": "search",
                "srsearch": q,
                "format": "json"
            }
            res = requests.get(url_wiki, params=params_search, timeout=4).json()
            search_hits = res.get("query", {}).get("search", [])
            for hit in search_hits[:3]:
                snippet_limpo = re.sub(r'<[^>]+>', ' ', hit.get('snippet', ''))
                texto_compilado += f" {hit.get('title', '')} {snippet_limpo}"
        except Exception:
            pass

        try:
            url_ddg = "https://html.duckduckgo.com/html/"
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            data = {"q": q}
            resp = requests.post(url_ddg, data=data, headers=headers, timeout=4)
            if resp.status_code == 200:
                snippets = re.findall(r'class="result__snippet[^">]*">(.*?)</a>', resp.text, re.DOTALL)
                for snip in snippets:
                    snippet_limpo = re.sub(r'<[^>]+>', ' ', snip)
                    texto_compilado += f" {snippet_limpo}"
        except Exception:
            pass

        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(q, max_results=3))
                for r in results:
                    texto_compilado += f" {r.get('title', '')} {r.get('body', '')}"
        except Exception:
            pass

    return texto_compilado

def analisar_proximidade_cargo(texto_bruto, nome_pesquisado):
    """Analisa cargos públicos e rastreia termos de parentesco para enquadramento."""
    texto_norm = normalizar_texto(texto_bruto)
    nome_norm = normalizar_texto(nome_pesquisado)

    if not texto_norm or not nome_norm:
        return None, None

    cargos_pep = [
        "senador", "senadora", "deputado", "deputada", "governador", "governadora", 
        "prefeito", "prefeita", "vice prefeito", "vice prefeita", "vice governadora", "ministro", "ministra", 
        "desembargador", "desembargadora", "juiz", "juiza", "juiz federal", "procurador", 
        "procuradora", "secretario", "secretaria", "vereador", "vereadora", "magistrado", 
        "magistrada", "parlamentar", "ex ministro", "ex senador", "ex deputado", "ex governador", 
        "ex prefeito", "politico", "politica", "suplente", "candidato", "candidata", "vice",
        "diretorio nacional", "diretorio estadual", "executiva nacional", "executiva estadual",
        "presidente de partido", "presidente partidario", "dirigente partidario",
        "membro da executiva", "membro do diretorio", "partido politico"
    ]

    termos_parentesco = [
        "filho do", "filho da", "filho de", "filha do", "filha da", "filha de",
        "esposa do", "esposa da", "esposa de", "esposo do", "esposo de",
        "conjuge do", "conjuge de", "marido do", "marido de",
        "mulher do", "mulher de", "casado com", "casada com",
        "neto do", "neto de", "neta do", "neta de",
        "sobrinho do", "sobrinho de", "sobrinha do", "sobrinha de",
        "herdeiro do", "herdeiro de", "pai do", "pai de", "mae do", "mae de",
        "irmao do", "irmao de", "irma do", "irma de", "parente de", "parente do"
    ]

    partes = nome_norm.split()
    variantes_nome = [nome_norm]
    if len(partes) >= 3:
        variantes_nome.append(f"{partes[0]} {partes[-1]}")
        variantes_nome.append(f"{partes[0]} {partes[-2]} {partes[-1]}")

    for var in variantes_nome:
        indices = [m.start() for m in re.finditer(re.escape(var), texto_norm)]
        for idx in indices:
            inicio_janela = max(0, idx - 350)
            fim_janela = min(len(texto_norm), idx + len(var) + 350)
            trecho = texto_norm[inicio_janela:fim_janela]

            for cargo in cargos_pep:
                if cargo in trecho:
                    tem_relacao = any(rel in trecho for rel in termos_parentesco)
                    if tem_relacao:
                        return "FAMILIAR", cargo.title()
                    return "DIRETO", cargo.title()

    return None, None

def verificar_pep_completo(nome_input, cpf_input):
    """Mecanismo Unificado que diferencia PEP DIRETO de PEP INDIRETO."""
    nome_limpo = nome_input.strip()
    nome_norm = normalizar_texto(nome_limpo)
    
    nome_chave_upper = nome_norm.upper()
    for chave_nat, dados_nat in BASE_PEP_NATIVA.items():
        if normalizar_texto(chave_nat).upper() == nome_chave_upper:
            return dados_nat

    match_planilha = buscar_na_planilha_pep(nome_limpo, cpf_input)
    if match_planilha:
        return {
            "tipo": "DIRETO",
            "cargo": match_planilha["cargo"],
            "orgao": match_planilha["orgao"],
            "detalhe": "Cadastro Ativo na Base Oficial do Governo Federal (CGU)",
            "origem": f"Base Oficial de PEPs ({match_planilha['detalhe']})"
        }

    texto_web_direto = buscar_web_robusta(nome_limpo)
    tipo_web, cargo_web = analisar_proximidade_cargo(texto_web_direto, nome_limpo)
    
    if cargo_web:
        if tipo_web == "FAMILIAR":
            return {
                "tipo": "FAMILIAR",
                "sufixo": "PARENTESCO",
                "cargo": f"Vínculo Familiar de 1º Grau (Parentesco com Agente Político Exposto: {cargo_web})",
                "orgao": "Administração Pública / Registro Histórico",
                "detalhe": "Vínculo Direto de Parentesco com Agente Político Mapeado na Web",
                "origem": "Mapeamento de Vínculos Familiares em Fontes Públicas"
            }
        else:
            return {
                "tipo": "DIRETO",
                "cargo": f"Agente Político / Exposição Direta ({cargo_web})",
                "orgao": "Administração Pública / Órgão Partidário",
                "detalhe": "Histórico Mapeado em Fontes Públicas e Notícias Web",
                "origem": "Pesquisa em Portais Públicos e Notícias Web"
            }

    sufixos_familiares = ["junior", "jr", "filho", "neto", "sobrinho"]
    palavras = nome_norm.split()
    
    if len(palavras) > 1 and palavras[-1] in sufixos_familiares:
        sufixo_encontrado = palavras[-1].upper()
        if sufixo_encontrado == "JR":
            sufixo_encontrado = "JUNIOR"
            
        palavras_orig = nome_limpo.split()
        nome_pai_orig = " ".join(palavras_orig[:-1])

        match_pai_planilha = buscar_na_planilha_pep(nome_pai_orig, "")
        if match_pai_planilha:
            return {
                "tipo": "FAMILIAR",
                "sufixo": sufixo_encontrado,
                "nome_parente": nome_pai_orig,
                "cargo": f"Vínculo Familiar de 1º Grau ({sufixo_encontrado.capitalize()} de Agente Político Exposto: {match_pai_planilha['cargo']})",
                "orgao": match_pai_planilha["orgao"],
                "detalhe": f"Vínculo Direto com PEP Mapeado na Base Oficial da CGU ({nome_pai_orig})",
                "origem": f"Mapeamento de Parentesco e Base Oficial da CGU ({nome_pai_orig})"
            }

        nomes_pai_testar = [nome_pai_orig]
        partes_pai = normalizar_texto(nome_pai_orig).split()
        if len(partes_pai) >= 3:
            nomes_pai_testar.append(f"{partes_pai[0].capitalize()} {partes_pai[-1].capitalize()}")

        for n_pai in nomes_pai_testar:
            texto_web_pai = buscar_web_robusta(n_pai)
            _, cargo_pai_web = analisar_proximidade_cargo(texto_web_pai, n_pai)

            if cargo_pai_web:
                return {
                    "tipo": "FAMILIAR",
                    "sufixo": sufixo_encontrado,
                    "nome_parente": n_pai,
                    "cargo": f"Vínculo Familiar de 1º Grau ({sufixo_encontrado.capitalize()} de Agente Político Exposto: {cargo_pai_web})",
                    "orgao": "Administração Pública / Registro Histórico",
                    "detalhe": f"Vínculo Direto de Parentesco com Agente Político Mapeado na Web ({n_pai})",
                    "origem": f"Mapeamento de Vínculos Familiares em Fontes Públicas ({n_pai})"
                }

    return None

# -----------------------------------------------------------------------------
# 🔑 CONFIGURAÇÃO DE ACESSO E AUTENTICAÇÃO
# -----------------------------------------------------------------------------
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
if "senha_hash_logada" not in st.session_state:
    st.session_state.senha_hash_logada = None
if "renovar_nome" not in st.session_state:
    st.session_state.renovar_nome = ""
if "renovar_cpf" not in st.session_state:
    st.session_state.renovar_cpf = ""

# --- TELA DE LOGIN E PRIMEIRO ACESSO COM SENHA INDIVIDUAL ---
if not st.session_state.autenticado:
    col_l1, col_l2, col_l3 = st.columns([1, 2, 1])
    with col_l2:
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.image("logo_bks.png" if os.path.exists("logo_bks.png") else "https://via.placeholder.com/300x80?text=BKS+Compliance", width=260)
        st.title("🛡️ Acesso ao Painel PLD/FTP")
        st.caption("Sistema de Conformidade e Prevenção à Lavagem de Dinheiro")
        st.markdown("---")
        
        email_digitado = st.text_input("📧 E-mail do Operador:", placeholder="seu.nome@bks.com.br").strip().lower()
        
        if email_digitado:
            if not verificar_email_autorizado(email_digitado):
                st.error("⚠️ **Acesso Negado:** O e-mail informado não possui permissão de acesso. Contate um administrador de compliance.")
            else:
                senha_hash_banco, cargo_banco = buscar_senha_usuario_banco(email_digitado)
                
                if not senha_hash_banco:
                    st.info("🆕 **Primeiro Acesso Detectado:** Crie sua senha de acesso individual abaixo.")
                    nova_senha = st.text_input("🔑 Crie sua Nova Senha:", type="password")
                    confirma_senha = st.text_input("🔑 Confirme a Nova Senha:", type="password")
                    
                    if st.button("✅ Cadastrar Senha e Entrar", use_container_width=True):
                        valida_comp, msg_comp = validar_complexidade_senha(nova_senha)
                        if not valida_comp:
                            st.warning(f"⚠️ {msg_comp}")
                        elif nova_senha != confirma_senha:
                            st.error("As senhas digitadas não conferem. Digite novamente.")
                        else:
                            cargo_usr = obter_cargo_usuario(email_digitado)
                            if cadastrar_senha_usuario_banco(email_digitado, nova_senha, cargo_usr):
                                st.success("Senha cadastrada com sucesso! Acessando o sistema...")
                                st.session_state.autenticado = True
                                st.session_state.email_logado = email_digitado
                                st.session_state.senha_hash_logada = gerar_hash_senha(nova_senha)
                                st.rerun()
                else:
                    senha_digitada = st.text_input("🔑 Senha de Acesso Individual:", type="password")
                    if st.button("🔓 Entrar no Sistema", use_container_width=True):
                        hash_digitada = gerar_hash_senha(senha_digitada)
                        if hash_digitada == senha_hash_banco or (SENHA_GERAL and senha_digitada.strip() == SENHA_GERAL):
                            st.session_state.autenticado = True
                            st.session_state.email_logado = email_digitado
                            st.session_state.senha_hash_logada = hash_digitada
                            st.rerun()
                        else:
                            st.error("❌ Senha incorreta! Verifique seus dados de acesso.")
        else:
            st.caption("💡 *Digite seu e-mail institucional corporativo para habilitar a senha.*")

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
    
    # Notificação de sucesso ao alterar a senha
    if "msg_sucesso_senha" in st.session_state:
        st.success(st.session_state.pop("msg_sucesso_senha"))

    # --- MÓDULO RETRÁTIL: ALTERAR MINHA SENHA ---
    with st.expander("🔑 Alterar Minha Senha", expanded=False):
        with st.form("form_mudar_senha_limpo", clear_on_submit=True):
            senha_atual_in = st.text_input("Senha Atual:", type="password")
            nova_senha_in = st.text_input("Nova Senha:", type="password")
            conf_senha_in = st.text_input("Confirmar Nova Senha:", type="password")
            
            btn_salvar_senha = st.form_submit_button("💾 Atualizar Senha", use_container_width=True)
            
            if btn_salvar_senha:
                hash_atual_input = gerar_hash_senha(senha_atual_in)
                hash_banco_usr, _ = buscar_senha_usuario_banco(st.session_state.email_logado)
                hash_sessao = st.session_state.get("senha_hash_logada", "")
                
                # Validação tripla: via sessão em memória, via banco Supabase ou via Senha Master
                senha_valida = (
                    (hash_sessao and hash_atual_input == hash_sessao) or
                    (hash_banco_usr and hash_atual_input == hash_banco_usr) or
                    (SENHA_GERAL and senha_atual_in.strip() == SENHA_GERAL)
                )
                valida_comp, msg_comp = validar_complexidade_senha(nova_senha_in)
                
                if not senha_valida:
                    st.error("❌ Senha atual incorreta.")
                elif not valida_comp:
                    st.warning(f"⚠️ {msg_comp}")
                elif nova_senha_in != conf_senha_in:
                    st.error("❌ A confirmação não confere com a nova senha.")
                else:
                    if cadastrar_senha_usuario_banco(st.session_state.email_logado, nova_senha_in, cargo_usuario_logado):
                        st.session_state["senha_hash_logada"] = gerar_hash_senha(nova_senha_in)
                        st.session_state["msg_sucesso_senha"] = "✅ Sua senha foi alterada com sucesso!"
                        st.rerun()
        
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
        st.session_state.senha_hash_logada = None
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
            # Cross-Validation de Coerência entre Nome e CPF
            coerente, msg_erro_coerencia = validar_coerencia_nome_cpf(nome_input, cpf_input)
            
            if not coerente:
                st.error(f"❌ **Incompatibilidade de Dados Identificada:**\n\n{msg_erro_coerencia}\n\n*Por segurança regulatória, a emissão do laudo foi suspensa para evitar cadastro de CPF incorreto.*")
            else:
                with st.spinner("🔎 Consultando base oficial e realizando varredura web de governança..."):
                    
                    nome_limpo = nome_input.strip()
                    res_pep = verificar_pep_completo(nome_limpo, cpf_input)

                    SITUACAO_CPF = "VÁLIDO"
                    tz_bsb = timezone(timedelta(hours=-3))
                    agora_dt = datetime.now(tz_bsb)

                    if res_pep:
                        STATUS_PEP_BANCO = "SIM"
                        
                        if res_pep["tipo"] == "DIRETO":
                            STATUS_PEP_DIRETO = "SIM"
                            PEP_VINCULO = "NÃO CONSTA"
                            RELACAO_2GRAU = "Sem vínculos adicionais"
                        else: # FAMILIAR / VÍNCULO INDIRETO
                            STATUS_PEP_DIRETO = "NÃO"
                            PEP_VINCULO = "INDIRETO"
                            RELACAO_2GRAU = "Relacionamento próximo"

                        CARGOS_EXERCIDOS = res_pep["cargo"]
                        ORGAO_ENTIDADE = res_pep["orgao"]
                        DETALHE_EXPOSICAO = res_pep["detalhe"]
                        ORIGEM_IDENTIFICACAO = res_pep["origem"]
                        RISCO_FINAL = "ALTO RISCO"
                        PRAZO_RENOVAÇÃO = "06 MESES"
                        APONTAMENTOS = f"RESTRIÇÃO: Exposição ativa ou vínculo indireto de parentesco com PEP ({ORIGEM_IDENTIFICACAO})"
                        PERFIL_OP = "Pessoa Politicamente Exposta (PEP)"
                        PARECER = f"Identificado enquadramento regulatório de PEP ({CARGOS_EXERCIDOS}). Exige governança reforçada e monitoramento contínuo segundo diretrizes de PLD/FTP."
                        PROXIMA_ATUALIZACAO = (agora_dt + timedelta(days=180)).strftime('%d/%m/%Y')
                    else:
                        STATUS_PEP_BANCO = "NÃO"
                        STATUS_PEP_DIRETO = "NÃO"
                        PEP_VINCULO = "NÃO CONSTA"
                        RELACAO_2GRAU = "Sem vínculos mapeados"
                        CARGOS_EXERCIDOS = "Nenhum cargo público detectado"
                        ORGAO_ENTIDADE = "Sem vínculo identificado"
                        DETALHE_EXPOSICAO = "Sem histórico de exposição pública registrado"
                        ORIGEM_IDENTIFICACAO = "Pesquisa em Portais Públicos e Notícias Web"
                        RISCO_FINAL = "BAIXO"
                        PRAZO_RENOVAÇÃO = "01 ANO"
                        APONTAMENTOS = "SEM RESTRIÇÕES: Nada consta na base oficial da CGU nem nos portais de transparência"
                        PERFIL_OP = "Profissional Independente"
                        PARECER = "Consulta realizada na base oficial de transparência da CGU e portais públicos. Não foram identificados cargos políticos ativos nem histórico de exposição pública para o Nome e CPF informados."
                        PROXIMA_ATUALIZACAO = (agora_dt + timedelta(days=365)).strftime('%d/%m/%Y')

                    # REGISTRA NO SUPABASE
                    registrar_vencimento(
                        nome=nome_input,
                        cpf_raw=cpf_input,
                        email_operador=st.session_state.email_logado,
                        status_pep=STATUS_PEP_BANCO,
                        data_emissao_dt=agora_dt,
                        data_vencimento_str=PROXIMA_ATUALIZACAO
                    )

                    st.markdown("---")
                    if res_pep:
                        st.error(f"🔴 **RESULTADO: PESSOA POLITICAMENTE EXPOSTA ({'PEP DIRETO' if res_pep['tipo']=='DIRETO' else 'PEP INDIRETO / VÍNCULO FAMILIAR'})** | Cargo: {CARGOS_EXERCIDOS} | Origem: {ORIGEM_IDENTIFICACAO}")
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
                        if key in ['STATUS_PEP', 'RISCO_FINAL', 'PRAZO_RENOVAÇÃO', 'RELACAO_2GRAU', 'PEP_VINCULO']:
                            bg_col = "#28a745"
                            if u in ['SIM', 'INDIRETO', 'SIM - INDIRETO', 'ALTO RISCO', '06 MESES', 'RELACIONAMENTO PRÓXIMO', 'RELACIONAMENTO PROXIMO', 'SINALIZADO']:
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
                        ("STATUS PEP DIRETO", STATUS_PEP_DIRETO, "STATUS_PEP"),
                        ("STATUS POR VÍNCULO", PEP_VINCULO, "PEP_VINCULO"),
                        ("ÓRGÃO / ENTIDADE DE ATUAÇÃO", ORGAO_ENTIDADE),
                        ("ENQUADRAMENTO DO CARGO", DETALHE_EXPOSICAO)
                    ])

                    make_sec("3. MAPEAMENTO DE VÍNCULOS FAMILIARES E EMPRESARIAIS", [
                        ("RELAÇÃO 2º GRAU PEP", RELACAO_2GRAU, "RELACAO_2GRAU"),
                        ("SOCIEDADES E PARTICIPAÇÕES", "Sem restrições ativas")
                    ])

                    make_sec("4. PERFIL EMPRESARIAL E SETOR DE ATUAÇÃO (RISCO OPERACIONAL)", [
                        ("PERFIL OPERACIONAL", PERFIL_OP),
                        ("REGIÃO DE ATUAÇÃO", "Brasil"),
                        ("SITUAÇÃO CADASTRAL CPF", SITUACAO_CPF),
                        ("APONTAMENTOS / RESTRIÇÕES", APONTAMENTOS)
                    ])

                    alerta_gerencia = "Obrigatório solicitar aprovação da gerência antes de prosseguir com as tratativas de seguro." if res_pep else None

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
        st.subheader("🔍 Filtros Avançados de Busca")

        col_f1, col_f2 = st.columns([1.5, 2])
        with col_f1:
            tipo_filtro = st.selectbox(
                "Filtrar por Campo ou Status:",
                [
                    "Todos os Campos",
                    "🔴 Apenas Vencidos",
                    "🟡 Vencem em breve",
                    "🟢 Apenas Válidos",
                    "👤 Nome Completo",
                    "📄 CPF",
                    "🛡️ Status PEP",
                    "📅 Data de Emissão",
                    "⏰ Data de Vencimento",
                    "📧 Operador"
                ]
            )
        with col_f2:
            termo_busca = st.text_input("Digite o termo para buscar:", placeholder="Digite nome, CPF, operador, data ou PEP...")

        dados_filtrados = []
        for item in dados_processados:
            if tipo_filtro == "🔴 Apenas Vencidos" and "🔴" not in item["Status do Prazo"]:
                continue
            elif tipo_filtro == "🟡 Vencem em breve" and "🟡" not in item["Status do Prazo"]:
                continue
            elif tipo_filtro == "🟢 Apenas Válidos" and "🟢" not in item["Status do Prazo"]:
                continue

            if termo_busca.strip():
                tb_norm = normalizar_texto(termo_busca)
                tb_limpo_num = re.sub(r'\D', '', termo_busca)

                if tipo_filtro == "👤 Nome Completo":
                    if tb_norm not in normalizar_texto(item["Nome Completo"]):
                        continue
                elif tipo_filtro == "📄 CPF":
                    cpf_limpo_item = re.sub(r'\D', '', item["CPF_Real"])
                    if tb_limpo_num not in cpf_limpo_item and tb_norm not in normalizar_texto(item["CPF_Exibicao"]):
                        continue
                elif tipo_filtro == "🛡️ Status PEP":
                    if tb_norm not in normalizar_texto(item["Status PEP"]):
                        continue
                elif tipo_filtro == "📅 Data de Emissão":
                    if tb_norm not in normalizar_texto(item["Data de Emissão"]):
                        continue
                elif tipo_filtro == "⏰ Data de Vencimento":
                    if tb_norm not in normalizar_texto(item["Data de Vencimento"]):
                        continue
                elif tipo_filtro == "📧 Operador":
                    if tb_norm not in normalizar_texto(item["Operador"]):
                        continue
                elif tipo_filtro in ["Todos os Campos", "🔴 Apenas Vencidos", "🟡 Vencem em breve", "🟢 Apenas Válidos"]:
                    in_nome = tb_norm in normalizar_texto(item["Nome Completo"])
                    cpf_limpo_item = re.sub(r'\D', '', item["CPF_Real"])
                    in_cpf = (tb_limpo_num != "" and tb_limpo_num in cpf_limpo_item) or tb_norm in normalizar_texto(item["CPF_Exibicao"])
                    in_pep = tb_norm in normalizar_texto(item["Status PEP"])
                    in_emis = tb_norm in normalizar_texto(item["Data de Emissão"])
                    in_venc = tb_norm in normalizar_texto(item["Data de Vencimento"])
                    in_oper = tb_norm in normalizar_texto(item["Operador"])

                    if not (in_nome or in_cpf or in_pep or in_emis or in_venc or in_oper):
                        continue

            dados_filtrados.append(item)

        st.markdown("<br>", unsafe_allow_html=True)
        st.subheader("📋 Relatórios Cadastrados")

        if not dados_filtrados:
            st.warning("Nenhum registro localizado com os filtros selecionados.")
        else:
            col_h1, col_h2, col_h3, col_h4, col_h5, col_h6, col_h7, col_h8 = st.columns([2.2, 1.2, 0.8, 1.1, 1.1, 1.1, 1.5, 0.8])
            with col_h1:
                st.markdown("**👤 Nome Completo**")
            with col_h2:
                st.markdown("**📄 CPF (LGPD)**")
            with col_h3:
                st.markdown("**🛡️ PEP**")
            with col_h4:
                st.markdown("**📅 Emissão**")
            with col_h5:
                st.markdown("**⏰ Vencimento**")
            with col_h6:
                st.markdown("**📌 Status Prazo**")
            with col_h7:
                st.markdown("**📧 Operador**")
            with col_h8:
                st.markdown("**⚡ Ação**")
            st.markdown("<hr style='margin-top:2px; margin-bottom:8px;'>", unsafe_allow_html=True)

            for idx, item in enumerate(dados_filtrados):
                c_n, c_c, c_p, c_e, c_v, c_s, c_o, c_b = st.columns([2.2, 1.2, 0.8, 1.1, 1.1, 1.1, 1.5, 0.8])
                
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
                with c_o:
                    st.write(f"`{item['Operador']}`")
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
