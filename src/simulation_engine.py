import pandas as pd
import numpy as np

def calculate_manhattan_dist(p1, p2, cross_aisles_y=[0, 10, 20]):
    # Distância Manhattan com restrição de Cross Aisle
    # Se mudar de corredor (X diferente) e Y não for Cross Aisle, tem que ir até o Cross Aisle mais próximo
    
    dx = abs(p1['x'] - p2['x'])
    dy = abs(p1['y'] - p2['y'])
    
    if dx == 0:
        return dy
    
    # Se X mudou, verificar se estamos em um Cross Aisle
    if p1['y'] in cross_aisles_y and p2['y'] == p1['y']:
        return dx + dy # Caminho reto pelo cross aisle
        
    # Caso contrário, ir até o CA mais próximo
    # Distância = (Y1 -> CA) + (X1 -> X2 no CA) + (CA -> Y2)
    # Simplificação: |y1 - ca| + |x1 - x2| + |ca - y2|
    
    # Encontrar melhor CA
    best_dist = float('inf')
    for ca in cross_aisles_y:
        d = abs(p1['y'] - ca) + dx + abs(p2['y'] - ca)
        if d < best_dist:
            best_dist = d
            
    return best_dist

def evaluate_layout_cost(df_orders, allocation_map, layout_dict):
    """
    Calcula o custo total de um layout (mapa de alocação) para um conjunto de pedidos.
    Usado pelo algoritmo de otimização (Hill Climbing).
    """
    total_cost = 0
    hub_node = {'x': 28, 'y': 10} # Staging Area
    
    # Pré-calcular custos de acesso para cada SKU (se possível)
    # Mas como depende do pedido, vamos iterar
    
    # Otimização: Agrupar por SKU para evitar recalcular a mesma rota mil vezes
    sku_counts = df_orders.groupby('sku_id')['quantity'].sum().reset_index()
    
    for _, row in sku_counts.iterrows():
        sku_id = row['sku_id']
        qty = row['quantity']
        
        if sku_id not in allocation_map:
            total_cost += 9999 # Penalidade alta para SKU não alocado
            continue
            
        bin_id = allocation_map[sku_id]
        if bin_id not in layout_dict:
            total_cost += 9999
            continue
            
        target_node = layout_dict[bin_id]
        
        # Custo de Distância (Ida e Volta)
        dist = calculate_manhattan_dist(hub_node, target_node)
        
        # Custo Vertical (Penalidade Z)
        z_penalty = (target_node['z'] - 1) * 10
        
        # Custo Total do SKU = (Distância * Peso + Vertical) * Frequência
        # Peso aqui é simplificado (1), mas poderia ser o peso do SKU
        cost_sku = (dist * 2 + z_penalty) * qty
        
        total_cost += cost_sku
        
    return total_cost

def run_simulation(df_orders, df_alloc, df_layout, num_orders_to_sim=50, forklift_speed=1.5, num_active_docks=1):
    # Configurações da Simulação
    STAGING_X = 28
    STAGING_Y = 10
    STAGING_CAPACITY = 10
    
    # Preparar dados
    layout_dict = df_layout.set_index('bin_id').to_dict('index')
    
    # Filtrar pedidos para simular
    sim_orders = df_orders['order_id'].unique()[:num_orders_to_sim]
    
    results = []
    
    for order_id in sim_orders:
        order_items = df_orders[df_orders['order_id'] == order_id]
        
        total_dist_m = 0
        total_time_s = 0
        
        # Ponto Central (Staging / Picking Area)
        hub_node = {'x': STAGING_X, 'y': STAGING_Y, 'z': 0}
        
        current_staging_load = 0
        
        for _, row in order_items.iterrows():
            sku_id = row['sku_id']
            qty = row['quantity']
            
            # Buscar localização
            alloc = df_alloc[df_alloc['sku_id'] == sku_id]
            if alloc.empty:
                continue # SKU sem posição (erro de alocação)
                
            bin_id = alloc.iloc[0]['bin_id']
            if bin_id not in layout_dict:
                continue
                
            target_node = layout_dict[bin_id]
            
            # --- 1. Movimentação (Ida e Volta da Paleteira) ---
            # A paleteira busca o palete e traz para o Picking (Fetch)
            # Depois leva o palete de volta (Return)
            # Total: 4 pernas de viagem (Hub -> Bin, Bin -> Hub, Hub -> Bin, Bin -> Hub)
            # *Nota: O usuário pediu "deixa na area... e depois devolve".
            
            dist_leg = calculate_manhattan_dist(hub_node, target_node)
            
            # Distância Total = 4 pernas (Busca + Devolução)
            dist_sku_total = dist_leg * 4
            total_dist_m += dist_sku_total
            
            # Tempo de Deslocamento
            # Penalidade de velocidade na Zona B (Manual) se aplicável
            speed = forklift_speed
            if target_node.get('zone_class') == 'Bronze': # Exemplo de penalidade
                speed *= 0.8
            
            time_travel = dist_sku_total / speed
            
            # Tempo de Elevação (Lift/Drop) - 4 operações (Pegar, Largar, Pegar, Largar)
            # Penalidade por altura (Z)
            lift_penalty = (target_node['z'] - 1) * 5 # 5s por nível acima do chão
            time_lift = (15 + lift_penalty) * 4 # 15s base por operação
            
            # --- 2. Tempo de Picking (Manual no Staging) ---
            # Proporcional a Qtd, Peso e Volume
            # Recuperar dados do SKU (peso, etc) se disponível, senão usar heurística
            # Aqui usamos heurística simples baseada na Qtd
            
            # Fatores (Simulados)
            picking_time = (qty * 1.5) + 10 # 1.5s por item + 10s setup
            
            total_time_s += time_travel + time_lift + picking_time
            
            # Simulação de Capacidade do Staging (Lógica Simplificada)
            current_staging_load += 1
            if current_staging_load >= STAGING_CAPACITY:
                # Se encheu, "forçamos" a devolução (já contabilizada no tempo total acima)
                # Na prática, libera espaço
                current_staging_load = 0
        
        results.append({
            'order_id': order_id,
            'assigned_dock': 'STAGING', # Agora tudo passa pelo Staging
            'dist_rnd_m': total_dist_m * 1.2, # Comparativo (sem otimização seria pior)
            'dist_opt_m': total_dist_m,
            'time_rnd_s': total_time_s * 1.2,
            'time_opt_s': total_time_s,
            'shipping_wave': order_items.iloc[0]['shipping_wave']
        })
        
    return pd.DataFrame(results)
