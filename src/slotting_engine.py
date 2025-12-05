import pandas as pd
import numpy as np
import random
from src import simulation_engine

def calculate_sku_scores(df_orders, df_skus, wave_weight_morning=1.5, wave_weight_afternoon=1.0):
    # Filtrar apenas SKUs que têm demanda (pedidos)
    active_skus = df_orders['sku_id'].unique()
    df_skus_active = df_skus[df_skus['sku_id'].isin(active_skus)]

    # Join Orders com SKU info
    df_process = df_orders.merge(df_skus_active[['sku_id', 'units_per_pallet']], on='sku_id', how='inner')

    # Calcular viagens (Trips)
    df_process['trips'] = np.ceil(df_process['quantity'] / df_process['units_per_pallet'])

    # Aplicar Peso da Onda
    df_process['wave_weight'] = df_process['shipping_wave'].apply(
        lambda x: wave_weight_morning if x == 'Morning' else wave_weight_afternoon
    )

    # Calcular Esforço Ponderado
    df_process['weighted_effort'] = df_process['trips'] * df_process['wave_weight']

    # Agrupar por SKU
    sku_scores = df_process.groupby('sku_id')['weighted_effort'].sum().reset_index()
    sku_scores.rename(columns={'weighted_effort': 'total_effort_score'}, inplace=True)

    # Adicionar informações de peso do pallet
    sku_scores = sku_scores.merge(df_skus_active[['sku_id', 'pallet_weight_kg']], on='sku_id', how='left')

    # Ordenar SKUs por Esforço (Decrescente)
    sku_scores = sku_scores.sort_values(by='total_effort_score', ascending=False).reset_index(drop=True)
    
    return sku_scores

def calculate_bin_costs(df_layout, forklift_speed=1.5):
    def calculate_vertical_penalty(z):
        if z == 1: return 0
        if z == 2: return 10
        if z == 3: return 20
        if z == 4: return 35
        return 999

    def calculate_weight_capacity(z):
        if z == 1: return 2000
        return 1000

    df_layout['vertical_penalty_sec'] = df_layout['z'].apply(calculate_vertical_penalty)
    df_layout['travel_time_sec'] = df_layout['distance_to_dock_meters'] / forklift_speed
    df_layout['total_cost_score'] = df_layout['travel_time_sec'] + df_layout['vertical_penalty_sec']
    df_layout['max_weight_kg'] = df_layout['z'].apply(calculate_weight_capacity)

    # Ordenar Bins por Custo (Crescente)
    df_layout = df_layout.sort_values(by='total_cost_score', ascending=True).reset_index(drop=True)
    
    return df_layout

def run_greedy_allocation(sku_scores, df_layout_sorted):
    allocation_map = []
    available_bins = df_layout_sorted.to_dict('records')
    assigned_bins = set()

    for index, sku in sku_scores.iterrows():
        sku_id = sku['sku_id']
        sku_weight = sku['pallet_weight_kg']
        
        assigned = False
        
        # Tentar encontrar o melhor bin disponível que suporte o peso
        # Note: available_bins já está ordenado por custo
        for i, bin_data in enumerate(available_bins):
            bin_id = bin_data['bin_id']
            
            if bin_id in assigned_bins:
                continue
                
            # Restrição de Peso
            if bin_data['max_weight_kg'] >= sku_weight:
                allocation_map.append({
                    'sku_id': sku_id,
                    'bin_id': bin_id,
                    'sku_effort': sku['total_effort_score'],
                    'bin_cost': bin_data['total_cost_score']
                })
                assigned_bins.add(bin_id)
                # Remover da lista para otimizar próximas iterações
                available_bins.pop(i)
                assigned = True
                break
        
        if not assigned:
            # Pode retornar um log ou warning se necessário
            pass

    return pd.DataFrame(allocation_map)

def run_slotting_strategy(df_skus, df_orders, df_layout):
    """
    Executa a estratégia completa de slotting:
    1. Calcula Score de Popularidade dos SKUs
    2. Calcula Custo dos Bins
    3. Realiza Alocação Gulosa (Greedy)
    """
    # 1. Calcular Scores
    sku_scores = calculate_sku_scores(df_orders, df_skus)
    
    # 2. Calcular Custos dos Bins
    df_layout_sorted = calculate_bin_costs(df_layout)
    
    # 3. Alocar
    df_alloc = run_greedy_allocation(sku_scores, df_layout_sorted)
    
    return df_alloc

def optimize_slotting_hill_climbing(current_alloc, df_orders, df_layout, iterations=50, sample_size=20):
    """
    Otimiza o slotting usando simulação (Hill Climbing).
    """
    # 1. Preparar Dados
    layout_dict = df_layout.set_index('bin_id').to_dict('index')
    
    # Sample de pedidos para ser rápido
    sample_order_ids = df_orders['order_id'].sample(n=sample_size, random_state=42).unique()
    df_orders_sample = df_orders[df_orders['order_id'].isin(sample_order_ids)]
    
    # Mapa atual (SKU -> Bin)
    current_map = current_alloc.set_index('sku_id')['bin_id'].to_dict()
    
    # Custo Inicial
    current_cost = simulation_engine.evaluate_layout_cost(df_orders_sample, current_map, layout_dict)
    
    history = [current_cost]
    best_map = current_map.copy()
    best_cost = current_cost
    
    skus = list(current_map.keys())
    
    for i in range(iterations):
        # 2. Perturbação: Trocar 2 SKUs de lugar
        sku_a, sku_b = random.sample(skus, 2)
        
        bin_a = current_map[sku_a]
        bin_b = current_map[sku_b]
        
        # Trocar
        current_map[sku_a] = bin_b
        current_map[sku_b] = bin_a
        
        # 3. Avaliar Novo Custo
        new_cost = simulation_engine.evaluate_layout_cost(df_orders_sample, current_map, layout_dict)
        
        # 4. Decisão (Hill Climbing: Aceita se melhor)
        if new_cost < best_cost:
            best_cost = new_cost
            best_map = current_map.copy()
            # Mantém a troca
        else:
            # Desfaz a troca
            current_map[sku_a] = bin_a
            current_map[sku_b] = bin_b
            
        history.append(best_cost)
        
    # Converter melhor mapa de volta para DataFrame
    optimized_alloc_list = [{'sku_id': k, 'bin_id': v} for k, v in best_map.items()]
    df_optimized = pd.DataFrame(optimized_alloc_list)
    
    # Recuperar metadados perdidos (scores, etc) fazendo merge com o original
    df_optimized = df_optimized.merge(current_alloc[['sku_id', 'sku_effort']], on='sku_id', how='left')
    
    return df_optimized, history
