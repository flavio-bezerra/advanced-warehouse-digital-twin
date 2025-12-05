import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import numpy as np
import os
import datetime

# Importar módulos locais
from src import data_engine, slotting_engine, simulation_engine

# Configuração da Página
st.set_page_config(page_title="Gêmeo Digital do Armazém", layout="wide", page_icon="🏭")

# --- CSS Customizado para KPIs ---
st.markdown("""
<style>
    .kpi-card {
        background-color: #ffffff;
        border-radius: 12px;
        padding: 20px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.05);
        border-bottom: 4px solid #e0e0e0;
        text-align: center;
        margin-bottom: 20px;
        transition: all 0.3s ease;
        height: 180px; /* Altura fixa para uniformidade */
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: center;
    }
    .kpi-card:hover {
        transform: translateY(-5px);
        box-shadow: 0 8px 16px rgba(0,0,0,0.1);
    }
    .kpi-icon {
        font-size: 24px;
        margin-bottom: 10px;
    }
    .kpi-value {
        font-size: 28px;
        font-weight: 800;
        color: #2c3e50;
        margin: 5px 0;
    }
    .kpi-label {
        font-size: 13px;
        color: #7f8c8d;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    .kpi-delta {
        font-size: 12px;
        font-weight: 700;
        margin-top: 10px;
        padding: 4px 8px;
        border-radius: 4px;
        display: inline-block;
    }
    .delta-pos { background-color: #d4edda; color: #155724; }
    .delta-neg { background-color: #f8d7da; color: #721c24; }
    .delta-neu { background-color: #e2e3e5; color: #383d41; }
</style>
""", unsafe_allow_html=True)

def kpi_card(col, label, value, delta=None, icon="📊", color="#3498db"):
    delta_html = ""
    if delta:
        delta_class = "delta-neu"
        if "CRÍTICO" in str(delta) or "Ruim" in str(delta) or "Overload" in str(delta) or "-" in str(delta):
            delta_class = "delta-neg"
        elif "OK" in str(delta) or "Bom" in str(delta) or "%" in str(delta): # Assume % reduction is good
            delta_class = "delta-pos"
            
        delta_html = f"<div class='kpi-delta {delta_class}'>{delta}</div>"
    
    html = f"""
    <div class="kpi-card" style="border-bottom-color: {color};">
        <div class="kpi-icon">{icon}</div>
        <div class="kpi-label">{label}</div>
        <div class="kpi-value">{value}</div>
        {delta_html}
    </div>
    """
    col.markdown(html, unsafe_allow_html=True)

st.title("🏭 Advanced Warehouse Digital Twin - Hub-and-Spoke Simulation")
st.markdown("**Simulador Didático de Operações Logísticas: Slotting, Roteirização e Capacidade.**")

with st.expander("ℹ️ Entenda a Lógica da Simulação (Premissas e Regras)"):
    st.markdown("""
    Este simulador utiliza um modelo **"Hub-and-Spoke"** detalhado para representar operações reais de picking e expedição.
    
    ### 1. 🏗️ Layout Didático (Compacto)
    *   O armazém foi reduzido para facilitar a visualização (30 metros de profundidade).
    *   **Zonas:** Racks (Paletadeiras) e Shelves (Manual), divididos em corredores.
    *   **Infraestrutura:** Corredores Transversais (Cross Aisles) para manobra e Área de Staging Central.

    ### 2. 🚛 Lógica de Movimentação (Hub-and-Spoke)
    *   Diferente de um "Milk Run" (circuito), aqui simulamos o fluxo de **Abastecimento e Retorno**:
        1.  A empilhadeira sai do **Staging** (Hub).
        2.  Vai até o endereço do produto (**Fetch**).
        3.  Realiza o picking (tempo baseado em peso/volume).
        4.  Retorna ao **Staging** para depositar a carga (**Return**).
    *   Isso resulta em **4 pernas de viagem** por palete, aumentando o realismo do esforço logístico.

    ### 3. 📦 Pedidos e Capacidade
    *   **Carga de Caminhão:** Cada "Pedido" gerado representa uma carga de caminhão (máx. 30 paletes).
    *   **Volumetria:** Produtos têm dimensões físicas (unidades por palete). Itens leves ocupam menos paletes que itens pesados/volumosos.
    *   **Estoque Ativo:** O sistema de Slotting é inteligente e aloca no armazém **apenas** os produtos que têm demanda no cenário atual, liberando espaço inútil.

    **Por que isso é útil?** 
    Este modelo permite testar o impacto real de estratégias de alocação (colocar produtos populares perto do Hub) e dimensionar a frota necessária para suportar o intenso vai-e-vem das empilhadeiras.
    """)

# --- Sidebar: Parâmetros ---
st.sidebar.header("⚙️ Configurações")

with st.sidebar.expander("ℹ️ O que significam estes parâmetros?"):
    st.markdown("""
    *   **Número de Pedidos:** Total de cargas (caminhões) a serem processadas no mês.
    *   **Multiplicador de Demanda:** Aumenta a quantidade de itens dentro de cada pedido (simula sazonalidade/picos).
    *   **Amostra de Simulação:** Quantos pedidos serão simulados detalhadamente (rota a rota) para gerar os KPIs. *Simular todos seria muito lento.*
    *   **Velocidade da Empilhadeira:** Velocidade média de deslocamento em m/s.
    *   **Turno de Trabalho:** Horário de operação (impacta no cálculo de horas disponíveis da frota).
    *   **Número de Docas:** Quantas docas simultâneas podem operar (impacta filas).
    """)

# 1. Parâmetros de Geração de Dados (Cenário)
st.sidebar.subheader("1. Cenário (Dados)")
num_orders = st.sidebar.slider("Número de Pedidos", 100, 10000, 3000)
demand_multiplier = st.sidebar.slider("Sazonalidade (Mult. Demanda)", 0.5, 3.0, 1.0, 0.1)
btn_generate_data = st.sidebar.button("🔄 Gerar Novo Cenário de Dados")

# 2. Parâmetros de Operação e Simulação
st.sidebar.subheader("2. Operação & Simulação")
forklift_speed = st.sidebar.slider("Velocidade Empilhadeira (m/s)", 0.5, 5.0, 1.5, 0.1)
morning_weight = st.sidebar.slider("Peso Prioridade Manhã", 1.0, 3.0, 1.5, 0.1)
simulate_all = st.sidebar.checkbox("Simular Todos os Pedidos (Lento 🐢)", value=False)
if simulate_all:
    sim_sample_size = 999999
    st.sidebar.warning("⚠️ Simular todos os pedidos pode levar vários minutos!")
else:
    sim_sample_size = st.sidebar.slider("Amostra Simulação (TSP)", 10, 500, 50)

# 3. Parâmetros de Frota
st.sidebar.subheader("3. Capacidade & Frota")
num_forklifts = st.sidebar.slider("Número de Empilhadeiras", 1, 100, 5)

shift_start = st.sidebar.time_input("Início do Turno", datetime.time(6, 0))
shift_end = st.sidebar.time_input("Fim do Turno", datetime.time(22, 0))

# Calcular Duração
d1 = datetime.datetime.combine(datetime.date.today(), shift_start)
d2 = datetime.datetime.combine(datetime.date.today(), shift_end)

if d2 < d1:
    d2 += datetime.timedelta(days=1)

shift_duration_hours = (d2 - d1).total_seconds() / 3600
st.sidebar.info(f"Duração do Turno: {shift_duration_hours:.1f} h")

# Manter compatibilidade com o resto do código
shift_window_hours = shift_duration_hours

num_active_docks = st.sidebar.slider("Número de Docas Ativas", 1, 10, 1)

btn_run_sim = st.sidebar.button("🚀 Rodar Simulação (Slotting + TSP)")

# --- Otimização Avançada (Sidebar) ---
sim_ready = 'sim_results' in st.session_state
st.sidebar.markdown("---")
st.sidebar.subheader("🧠 Otimização")
btn_optimize = st.sidebar.button("✨ Otimização Avançada (Hill Climbing)", disabled=not sim_ready)

if sim_ready:
    with st.sidebar.expander("⚙️ Parâmetros da Otimização"):
        opt_iterations = st.slider("Iterações (Trocas)", 10, 200, 50)
        opt_sample = st.slider("Amostra de Pedidos", 5, 50, 20)
else:
    # Valores padrão para evitar erros se não renderizar
    opt_iterations = 50
    opt_sample = 20

# --- Funções Auxiliares ---
def check_data_files_exist():
    return (os.path.exists('data/layout_fisico.csv') and 
            os.path.exists('data/mestre_skus.csv') and 
            os.path.exists('data/pedidos_backlog.csv'))

def generate_and_save_data():
    with st.spinner("Gerando Layout, SKUs e Pedidos..."):
        df_layout = data_engine.generate_layout()
        # Quantidade de SKUs reduzida para 500 (Didático)
        df_skus = data_engine.generate_skus(num_skus=500)
        df_orders = data_engine.generate_orders(df_skus, num_orders=num_orders, demand_multiplier=demand_multiplier)
        
        # Salvar em disco
        df_layout.to_csv('data/layout_fisico.csv', index=False)
        df_skus.to_csv('data/mestre_skus.csv', index=False)
        df_orders.to_csv('data/pedidos_backlog.csv', index=False)
        
        st.success("Novos dados gerados e salvos com sucesso!")
        return df_layout, df_skus, df_orders

def load_data():
    df_layout = pd.read_csv('data/layout_fisico.csv')
    df_skus = pd.read_csv('data/mestre_skus.csv')
    df_orders = pd.read_csv('data/pedidos_backlog.csv')
    return df_layout, df_skus, df_orders

# --- Lógica Principal ---

# 1. Gerenciamento de Dados (Geração ou Carga)
if btn_generate_data:
    df_layout, df_skus, df_orders = generate_and_save_data()
elif not check_data_files_exist():
    st.warning("Arquivos de dados não encontrados. Gerando cenário inicial...")
    df_layout, df_skus, df_orders = generate_and_save_data()
else:
    # Carregar dados existentes silenciosamente (ou mostrar aviso se quiser)
    df_layout, df_skus, df_orders = load_data()
    st.info(f"Usando dados existentes: {len(df_orders)} pedidos carregados. (Clique em 'Gerar Novo Cenário' para atualizar com os sliders acima)")

# --- Análise de Demanda (Backlog Mensal) ---
st.header("📈 Análise de Demanda (Backlog Mensal)")

# Preparar dados para gráficos
df_demand_day = df_orders.groupby(['day', 'shipping_wave']).size().reset_index(name='count')
df_qty_day = df_orders.groupby('day')['quantity'].sum().reset_index(name='total_qty')

# Merge com SKUs para pegar categoria
if 'category' not in df_skus.columns:
    # Fallback para dados antigos
    df_skus['category'] = df_skus['description']

df_orders_cat = df_orders.merge(df_skus[['sku_id', 'category']], on='sku_id', how='left')
df_cat_demand = df_orders_cat.groupby('category')['quantity'].sum().reset_index().sort_values('quantity', ascending=False)

# Layout de Colunas para Gráficos

# 1. KPIs de Resumo (Topo)
total_items = df_orders['quantity'].sum()
total_orders = len(df_orders)
total_inventory_est = df_skus['units_per_pallet'].sum()
turnover = total_items / total_inventory_est if total_inventory_est > 0 else 0
days_on_hand = 30 / turnover if turnover > 0 else 0

st.markdown("### Resumo do Mês & Giro")
k1, k2, k3, k4, k5 = st.columns(5)
kpi_card(k1, "Total Pedidos", f"{total_orders:,}", icon="📦", color="#3498db")
kpi_card(k2, "Total Peças", f"{total_items:,.0f}", icon="🔢", color="#e67e22")
kpi_card(k3, "Estoque Médio", f"{total_inventory_est:,.0f}", icon="🏭", color="#9b59b6")
kpi_card(k4, "Giro de Estoque", f"{turnover:.2f}x", icon="🔄", color="#2ecc71")
kpi_card(k5, "Cobertura", f"{days_on_hand:.1f} dias", icon="📅", color="#f1c40f")

# 2. Gráfico de Volume Total (Full Width)
st.subheader("Volume Total de Itens por Dia")
fig_qty = px.line(df_qty_day, x='day', y='total_qty', markers=True,
                  title="Total de Peças Movimentadas por Dia",
                  labels={'day': 'Dia', 'total_qty': 'Qtd Peças'})
fig_qty.update_traces(line_color='green')
st.plotly_chart(fig_qty, use_container_width=True)

# 3. Gráficos Detalhados (Colunas)
col1, col2 = st.columns(2)

with col1:
    st.subheader("Pedidos por Dia (Turno)")
    fig_orders = px.bar(df_demand_day, x='day', y='count', color='shipping_wave', 
                        title="Volume de Pedidos Diário",
                        labels={'day': 'Dia', 'count': 'Qtd Pedidos', 'shipping_wave': 'Turno'})
    st.plotly_chart(fig_orders, use_container_width=True)

with col2:
    st.subheader("Demanda por Categoria")
    fig_cat = px.bar(df_cat_demand, x='quantity', y='category', orientation='h',
                     title="Top Categorias (Qtd Itens)",
                     labels={'quantity': 'Total Itens', 'category': 'Categoria'})
    fig_cat.update_layout(yaxis={'categoryorder':'total ascending'})
    st.plotly_chart(fig_cat, use_container_width=True)

# --- Simulação ---
if btn_run_sim:
    # 1. Alocação (Slotting)
    st.markdown("---")
    st.header("🧠 Executando Slotting Inteligente...")
    
    with st.spinner("Calculando melhores posições para cada SKU..."):
        df_alloc = slotting_engine.run_slotting_strategy(df_skus, df_orders, df_layout)
        st.success(f"Slotting Concluído! {len(df_alloc)} SKUs alocados.")
        
    # 2. Simulação de Movimentação
    st.header("👷🏻‍♀️ Simulando Operação (Hub-and-Spoke)...")
    
    with st.spinner(f"Simulando Rotas para {sim_sample_size} pedidos..."):
        df_kpis = simulation_engine.run_simulation(df_orders, df_alloc, df_layout, num_orders_to_sim=sim_sample_size, forklift_speed=forklift_speed, num_active_docks=num_active_docks)
        df_kpis.to_csv('data/kpis_simulacao.csv', index=False)
        
    st.session_state['sim_results'] = {
        'alloc': df_alloc,
        'kpis': df_kpis
    }
    st.success("Simulação Concluída!")

# --- Resultados da Simulação ---
if 'sim_results' in st.session_state:
    results = st.session_state['sim_results']
    df_alloc = results['alloc']
    df_kpis = results['kpis']
    
    # --- Otimização Avançada ---
    st.markdown("---")
    st.header("🧠 Otimização Avançada (Simulation-Based Optimization)")
    
    with st.expander("ℹ️ O que é Simulation-Based Optimization?"):
        st.markdown("""
        **É uma técnica poderosa onde o modelo de simulação é usado diretamente pelo algoritmo de otimização para avaliar a qualidade de uma solução.**
        
        Diferente da otimização matemática tradicional (que usa fórmulas estáticas), aqui nós **"rodamos o dia"** virtualmente para ver o que acontece.
        
        **Como funciona o algoritmo (Hill Climbing) neste Gêmeo Digital:**
        1.  **Perturbação:** O sistema escolhe aleatoriamente dois produtos e troca suas posições no armazém.
        2.  **Simulação:** Ele re-simula um conjunto de pedidos com esse novo layout.
        3.  **Avaliação:** Se o tempo total de operação diminuiu, a troca é **aceita** (o layout evoluiu). Se piorou, a troca é desfeita.
        4.  **Repetição:** Esse processo se repete por várias iterações, "escalando" a eficiência do armazém degrau por degrau.
        
        > *Utilize o botão **"✨ Otimização Avançada"** na barra lateral para iniciar este processo.*
        """)
    
    if btn_optimize:
        with st.spinner(f"Otimizando Layout... Testando {opt_iterations} cenários..."):
            df_alloc_optimized, history = slotting_engine.optimize_slotting_hill_climbing(
                df_alloc, df_orders, df_layout, iterations=opt_iterations, sample_size=opt_sample
            )
            
            st.session_state['sim_results']['alloc'] = df_alloc_optimized
            st.session_state['optimization_history'] = history
            
            df_kpis_new = simulation_engine.run_simulation(
                df_orders, df_alloc_optimized, df_layout, 
                num_orders_to_sim=sim_sample_size, 
                forklift_speed=forklift_speed, 
                num_active_docks=num_active_docks
            )
            
            # Atualizar KPIs para exibir os novos resultados
            avg_dist_old = df_kpis['dist_opt_m'].mean()
            avg_dist_new = df_kpis_new['dist_opt_m'].mean()
            avg_reduction_dist = ((avg_dist_old - avg_dist_new) / avg_dist_old) * 100 if avg_dist_old > 0 else 0
            
            avg_time_old = df_kpis['time_opt_s'].mean()
            avg_time_new = df_kpis_new['time_opt_s'].mean()
            avg_reduction_time = ((avg_time_old - avg_time_new) / avg_time_old) * 100 if avg_time_old > 0 else 0
            
            avg_time_per_order = avg_time_new
            
            # Persistir resultados otimizados
            st.session_state['sim_results']['kpis'] = df_kpis_new
            df_kpis = df_kpis_new # Atualizar referência local
            
    else:
        # Se não houve otimização agora, usar os dados atuais vs baseline (Random)
        avg_dist_rnd = df_kpis['dist_rnd_m'].mean()
        avg_dist_opt = df_kpis['dist_opt_m'].mean()
        avg_reduction_dist = ((avg_dist_rnd - avg_dist_opt) / avg_dist_rnd) * 100 if avg_dist_rnd > 0 else 0
        
        avg_time_rnd = df_kpis['time_rnd_s'].mean()
        avg_time_opt = df_kpis['time_opt_s'].mean()
        avg_reduction_time = ((avg_time_rnd - avg_time_opt) / avg_time_rnd) * 100 if avg_time_rnd > 0 else 0
        
        avg_time_per_order = avg_time_opt

    # --- KPIs de Eficiência ---
    st.markdown("---")
    st.subheader("📊 KPIs de Eficiência")
    
    with st.expander("ℹ️ Como esses KPIs são calculados?"):
        st.markdown("""
        *   **Redução Distância:** Comparação entre a distância percorrida no cenário atual (Otimizado) versus um cenário base (Aleatório ou Anterior).
        *   **Redução Tempo:** Economia de tempo estimada considerando deslocamento e elevação.
        *   **Tempo Médio/Pedido:** Tempo médio para completar um pedido (picking + transporte) no cenário atual.
        """)

    col1, col2, col3 = st.columns(3)
    kpi_card(col1, "Redução Distância", f"{avg_reduction_dist:.2f}%", icon="📏", color="#2ecc71")
    kpi_card(col2, "Redução Tempo", f"{avg_reduction_time:.2f}%", icon="⏱️", color="#2ecc71")
    kpi_card(col3, "Tempo Médio/Pedido", f"{avg_time_per_order:.1f} s", icon="📦", color="#3498db")

    # --- Dimensionamento da Frota ---
    st.header("🏭 Dimensionamento da Frota (Análise Diária)")
    
    avg_time_per_order = df_kpis['time_opt_s'].mean()
    df_daily_ops = df_orders.groupby('day').size().reset_index(name='num_orders')
    df_daily_ops['workload_hours'] = (df_daily_ops['num_orders'] * avg_time_per_order) / 3600
    
    daily_fleet_capacity_hours = num_forklifts * shift_window_hours
    df_daily_ops['capacity_hours'] = daily_fleet_capacity_hours
    df_daily_ops['utilization'] = (df_daily_ops['workload_hours'] / df_daily_ops['capacity_hours']) * 100
    df_daily_ops['status'] = df_daily_ops['utilization'].apply(lambda x: 'Overload' if x > 100 else 'OK')
    
    max_utilization = df_daily_ops['utilization'].max()
    days_overload = df_daily_ops[df_daily_ops['utilization'] > 100].shape[0]
    avg_utilization = df_daily_ops['utilization'].mean()
    
    max_workload = df_daily_ops['workload_hours'].max()
    suggested_fleet = np.ceil(max_workload / shift_window_hours)
    
    c1, c2, c3, c4 = st.columns(4)
    kpi_card(c1, "Utilização Média", f"{avg_utilization:.1f}%", icon="📉", color="#9b59b6")
    
    delta_peak = "CRÍTICO" if max_utilization > 100 else "OK"
    peak_color = "#e74c3c" if max_utilization > 100 else "#2ecc71"
    kpi_card(c2, "Utilização Pico", f"{max_utilization:.1f}%", delta=delta_peak, icon="🔥", color=peak_color)
    
    # KPIs de Planejamento Integrados
    total_days = df_daily_ops.shape[0]
    overload_days = df_daily_ops[df_daily_ops['status'] == 'Overload'].shape[0]
    df_plan = df_daily_ops.copy()
    df_plan['balance_hours'] = df_plan['capacity_hours'] - df_plan['workload_hours']
    total_balance = df_plan['balance_hours'].sum()
    
    delta_days = f"{overload_days} dias atraso" if overload_days > 0 else "OK"
    days_color = "#e67e22" if overload_days > 0 else "#2ecc71"
    kpi_card(c3, "Dias com Gargalo", f"{overload_days} / {total_days}", delta=delta_days, icon="⚠️", color=days_color)
    
    kpi_card(c4, "Balanço Mensal", f"{total_balance:.0f} h", delta="Sobra" if total_balance >= 0 else "Falta", icon="⚖️", color="#8e44ad" if total_balance >= 0 else "#c0392b")
    
    st.subheader("Carga de Trabalho vs. Capacidade (Dia a Dia)")
    fig_cap = go.Figure()
    fig_cap.add_trace(go.Bar(x=df_daily_ops['day'], y=df_daily_ops['workload_hours'], name='Carga de Trabalho (h)', marker_color=df_daily_ops['status'].map({'OK': 'green', 'Overload': 'red'})))
    fig_cap.add_trace(go.Scatter(x=df_daily_ops['day'], y=df_daily_ops['capacity_hours'], mode='lines', name='Capacidade da Frota', line=dict(color='blue', width=3, dash='dash')))
    fig_cap.update_layout(title="Balanço de Capacidade Diária", xaxis_title="Dia do Mês", yaxis_title="Horas de Trabalho", legend=dict(orientation="h", y=1.1))
    st.plotly_chart(fig_cap, use_container_width=True)

    # --- Heatmap de Estoque ---
    st.header("📦 Distribuição de Estoque (Mapa de Categorias)")
    df_full = df_layout.merge(df_alloc[['bin_id', 'sku_id']], on='bin_id', how='left').merge(df_skus, on='sku_id', how='left')
    if 'category' not in df_full.columns: df_full['category'] = df_full['description']
    df_full['category'] = df_full['category'].fillna('Vazio')
    
    cat_color_map = {
        'Vazio': 'lightgrey', 'Móveis': '#1f77b4', 'Eletrodomésticos': '#ff7f0e', 'Automotivo': '#2ca02c',
        'Construção': '#d62728', 'Eletrônicos': '#9467bd', 'Vestuário': '#8c564b', 'Alimentos': '#e377c2',
        'Farmácia': '#7f7f7f', 'Livros': '#bcbd22'
    }
    import plotly.colors as pc
    default_colors = pc.qualitative.Plotly
    
    fig_heat = go.Figure()
    for cat in sorted(df_full['category'].unique()):
        df_cat = df_full[df_full['category'] == cat]
        color = cat_color_map.get(cat, default_colors[hash(cat) % len(default_colors)])
        fig_heat.add_trace(go.Scatter(x=df_cat['x'], y=df_cat['y'], mode='markers', marker=dict(size=15, color=color, symbol='square'), text=df_cat['bin_id'] + "<br>" + df_cat['category'], name=cat))
    fig_heat.update_layout(
        title="Mapa de Localização", 
        xaxis_title="Corredor (X)", 
        yaxis_title="Profundidade (Y)", 
        height=600,
        plot_bgcolor='#f2f2f2', # Fundo cinza claro
        xaxis=dict(showgrid=True, gridcolor='white'),
        yaxis=dict(showgrid=True, gridcolor='white', scaleanchor="x", scaleratio=1) # Proporção real (Retangular)
    )
    st.plotly_chart(fig_heat, use_container_width=True)
    
    # --- Relatório de Alocação ---
    st.header("📋 Relatório de Alocação (Sugestão de Slotting)")
    df_report = df_alloc.merge(df_skus[['sku_id', 'category', 'popularity_score']], on='sku_id', how='left').merge(df_layout[['bin_id', 'zone_class', 'distance_to_dock_meters']], on='bin_id', how='left')
    if 'category' not in df_report.columns: df_report['category'] = 'Geral'
    df_zone_dist = df_report.groupby(['category', 'zone_class']).size().reset_index(name='count')
    fig_zone = px.bar(df_zone_dist, x='category', y='count', color='zone_class', title="Distribuição de Produtos nas Zonas", barmode='stack')
    st.plotly_chart(fig_zone, use_container_width=True)
    
    # --- Visualização 3D ---
    st.header("🏭 Visualização 3D do Armazém (Digital Twin)")
    fig_3d = go.Figure()
    fig_3d.add_trace(go.Mesh3d(x=[0, 30, 30, 0], y=[0, 0, 20, 20], z=[0, 0, 0, 0], color='lightgray', opacity=0.5, name='Piso'))
    
    for cat in sorted(df_full['category'].unique()):
        df_cat = df_full[df_full['category'] == cat]
        color = cat_color_map.get(cat, default_colors[hash(cat) % len(default_colors)])
        fig_3d.add_trace(go.Scatter3d(x=df_cat['x'], y=df_cat['y'], z=df_cat['z'], mode='markers', marker=dict(size=5, color=color, symbol='square', line=dict(width=1, color='DarkSlateGrey')), name=cat, text=df_cat['bin_id']))
        
    fig_3d.add_trace(go.Scatter3d(x=[30]*3, y=[5, 10, 15], z=[0]*3, mode='text', text=['Doca 1', 'Doca 2', 'Doca 3'], textposition="top center", name='Docas'))
    fig_3d.add_trace(go.Scatter3d(x=[28], y=[10], z=[0], mode='markers+text', marker=dict(size=10, color='gold', symbol='diamond'), text=['Staging (Hub)'], name='Staging'))
    fig_3d.update_layout(title="Gêmeo Digital 3D", scene=dict(xaxis_title='X', yaxis_title='Y', zaxis_title='Z', aspectmode='data'), height=700)
    st.plotly_chart(fig_3d, use_container_width=True)
    
    # --- Rotas ---
    st.header("👷🏻‍♀️ Simulação de Rotas (Hub-and-Spoke)")
    day_to_viz = st.slider("Selecione o Dia para Visualizar Rotas:", min_value=int(df_orders['day'].min()), max_value=int(df_orders['day'].max()), value=1)
    sim_orders_day = df_orders[df_orders['day'] == day_to_viz].head(20) # Limit to 20 orders for clarity
    
    # Identify SKUs involved in the selected day's simulation
    moved_sku_ids = sim_orders_day['sku_id'].unique()
    
    # Prepare Warehouse State Data
    # 1. Merge Layout with Allocation to see what's where
    df_warehouse_state = df_layout.merge(df_alloc, on='bin_id', how='left')
    
    # 2. Classify each bin
    def classify_bin(row):
        if pd.isna(row['sku_id']):
            return 'Vazio'
        elif row['sku_id'] in moved_sku_ids:
            return 'Movimentado'
        else:
            return 'Estático'
            
    df_warehouse_state['status'] = df_warehouse_state.apply(classify_bin, axis=1)
    
    # 3. Create Figure
    fig_routes = go.Figure()
    
    # 4. Plot Bins by Status
    # Empty (Gray)
    df_empty = df_warehouse_state[df_warehouse_state['status'] == 'Vazio']
    fig_routes.add_trace(go.Scatter3d(x=df_empty['x'], y=df_empty['y'], z=df_empty['z'], 
                                      mode='markers', marker=dict(size=3, color='lightgrey', opacity=0.3), 
                                      name='Vazio'))
                                      
    # Static (Blue)
    df_static = df_warehouse_state[df_warehouse_state['status'] == 'Estático']
    fig_routes.add_trace(go.Scatter3d(x=df_static['x'], y=df_static['y'], z=df_static['z'], 
                                      mode='markers', marker=dict(size=4, color='blue', opacity=0.5), 
                                      name='Estático (Sem Interação)'))
                                      
    # Moved (Red)
    df_moved = df_warehouse_state[df_warehouse_state['status'] == 'Movimentado']
    fig_routes.add_trace(go.Scatter3d(x=df_moved['x'], y=df_moved['y'], z=df_moved['z'], 
                                      mode='markers', marker=dict(size=6, color='red', symbol='square'), 
                                      name='Movimentado (Alvo)'))

    # 5. Plot Routes (Lines)
    # Hub Node
    fig_routes.add_trace(go.Scatter3d(x=[28], y=[10], z=[0], mode='markers', marker=dict(size=10, color='gold', symbol='diamond'), name='Hub (Staging)'))
    
    # Draw lines from Hub to Moved Bins
    sim_routes = sim_orders_day.merge(df_alloc, on='sku_id', how='left').merge(df_layout, on='bin_id', how='left')
    
    for i, row in sim_routes.iterrows():
        if pd.isna(row['bin_id']): continue
        # Line Hub -> Bin
        fig_routes.add_trace(go.Scatter3d(
            x=[28, row['x']], y=[10, row['y']], z=[0, row['z']], 
            mode='lines', 
            line=dict(color='red', width=3), 
            opacity=0.7, 
            showlegend=False,
            hoverinfo='none'
        ))

    # Layout improvements
    fig_routes.update_layout(
        title=f"Simulação 3D: Rotas do Dia {day_to_viz} (Hub-and-Spoke)", 
        scene=dict(xaxis_title='X', yaxis_title='Y', zaxis_title='Z', aspectmode='data'), 
        height=700,
        legend=dict(x=0, y=1)
    )
    st.plotly_chart(fig_routes, use_container_width=True)
        
    # --- Heatmap Tráfego ---
    st.header("🔥 Mapa de Calor de Tráfego")
    if not df_kpis.empty:
        max_x, max_y = 30, 20
        traffic_grid = np.zeros((max_x + 1, max_y + 1))
        
        # 1. Identificar pedidos simulados
        simulated_order_ids = df_kpis['order_id'].unique()
        
        # 2. Filtrar itens desses pedidos
        df_sim_items = df_orders[df_orders['order_id'].isin(simulated_order_ids)]
        
        # 3. Merge com Alocação e Layout para pegar coordenadas (X, Y)
        df_traffic = df_sim_items.merge(df_alloc, on='sku_id', how='left').merge(df_layout, on='bin_id', how='left')
        
        for _, row in df_traffic.iterrows():
            if pd.isna(row['x']): continue
            start_x, start_y = 28, 10
            end_x, end_y = int(row['x']), int(row['y'])
            
            step_x = 1 if end_x > start_x else -1
            for x in range(start_x, end_x, step_x): traffic_grid[x, 10] += 1
            
            if end_y != 10:
                step_y = 1 if end_y > 10 else -1
                for y in range(10, end_y, step_y): traffic_grid[end_x, y] += 1
            traffic_grid[end_x, end_y] += 1
            
        custom_colorscale = [[0.0, 'rgba(0,0,0,0)'], [0.01, 'rgba(255, 200, 200, 0.5)'], [0.5, 'rgba(255, 0, 0, 0.8)'], [1.0, 'rgba(100, 0, 0, 1.0)']]
        fig_heat_traffic = go.Figure(data=go.Heatmap(z=traffic_grid.T, x=list(range(max_x + 1)), y=list(range(max_y + 1)), colorscale=custom_colorscale))
        
        # Add Warehouse Layout Overlay
        shape_offset = 1.0
        warehouse_shapes = []
        for x in [10, 14, 18]: warehouse_shapes.append(dict(type="rect", x0=x-0.4+shape_offset, y0=0, x1=x+0.4+shape_offset, y1=20, line=dict(color="RoyalBlue", width=1), fillcolor="rgba(65, 105, 225, 0.05)"))
        for x in [22, 24, 26]: warehouse_shapes.append(dict(type="rect", x0=x-0.4+shape_offset, y0=0, x1=x+0.4+shape_offset, y1=10, line=dict(color="Green", width=1), fillcolor="rgba(0, 128, 0, 0.05)"))
        warehouse_shapes.append(dict(type="rect", x0=29.5+shape_offset, y0=0, x1=30.5+shape_offset, y1=20, line=dict(color="Black", width=1), fillcolor="rgba(0, 0, 0, 0.05)"))
        warehouse_shapes.append(dict(type="circle", x0=27+shape_offset, y0=9, x1=29+shape_offset, y1=11, line=dict(color="Orange", width=2)))
        for y in [0, 10, 20]: warehouse_shapes.append(dict(type="line", x0=0+shape_offset, y0=y, x1=30+shape_offset, y1=y, line=dict(color="Grey", width=1, dash="dot")))
        
        fig_heat_traffic.update_layout(title="Densidade de Tráfego", xaxis_title="X", yaxis_title="Y", height=600, shapes=warehouse_shapes, plot_bgcolor='#f2f2f2')
        st.plotly_chart(fig_heat_traffic, use_container_width=True)