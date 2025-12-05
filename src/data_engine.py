import pandas as pd
import numpy as np
import random

# Configuração de Semente para Reprodutibilidade
random.seed(42)
np.random.seed(42)

class WarehouseTopology:
    def __init__(self):
        self.nodes = []
        self._build_topology()

    def _build_topology(self):
        # --- ZONA A (Racks) - Paletadeiras (X <= 18) ---
        rack_xs = [10, 14, 18]
        for i, x in enumerate(rack_xs):
            aisle_id = f"R{i+1}"
            for y in range(21): # Y 0-20
                for z in range(1, 6):
                    self.nodes.append({
                        'bin_id': f"{aisle_id}_{y}_{z}",
                        'x': x, 'y': y, 'z': z, 'zone': 'A',
                        'aisle_id': aisle_id, 'type': 'Rack'
                    })

        # --- ZONA B (Shelving) - Manual (X > 18) ---
        shelving_xs = [22, 24, 26]
        for i, x in enumerate(shelving_xs):
            aisle_id = f"S{i+1}"
            for y in range(11): # Y 0-10
                for z in range(1, 6):
                    self.nodes.append({
                        'bin_id': f"{aisle_id}_{y}_{z}",
                        'x': x, 'y': y, 'z': z, 'zone': 'B',
                        'aisle_id': aisle_id, 'type': 'Shelf'
                    })
        
        # --- DEFINIÇÃO DE CROSS AISLES E DOCAS ---
        # Cross Aisles (Corredores Transversais para Manobra)
        self.cross_aisles_y = [0, 10, 20]
        
        # Docas (X=30, Y variando)
        self.dock_positions = []
        dock_ys = [20, 15, 10, 5, 0]
        for i, y in enumerate(dock_ys):
            self.dock_positions.append({'id': f"DOCK_{i+1}", 'x': 30, 'y': y, 'z': 1})

    def calculate_distance_to_dock(self, x, y):
        # Calcula a distância para a doca mais próxima (X=30)
        min_dist = float('inf')
        for dock in self.dock_positions:
            dist = abs(x - dock['x']) + abs(y - dock['y'])
            if dist < min_dist:
                min_dist = dist
        return min_dist

    def get_all_nodes_data(self):
        df = pd.DataFrame(self.nodes)
        df['distance_to_dock_meters'] = df.apply(lambda row: self.calculate_distance_to_dock(row['x'], row['y']), axis=1)
        
        # --- Classificação ABC do Layout (Zoning) ---
        # Definir zonas de performance baseadas na distância
        # Ajustado para Layout Didático (Compacto)
        def classify_bin(dist):
            if dist < 10: return 'Gold'   # Zonas muito próximas (ex: Shelving)
            if dist < 18: return 'Silver' # Zonas intermediárias (ex: Racks Frontais)
            return 'Bronze'               # Zonas fundas (ex: Racks Traseiros)
            
        df['zone_class'] = df['distance_to_dock_meters'].apply(classify_bin)
        return df

def generate_layout():
    topology = WarehouseTopology()
    df_layout = topology.get_all_nodes_data()
    return df_layout

def generate_skus(num_skus=500):
    skus = []
    # Distribuição Pareto (Model Stock)
    # 20% SKUs = Classe A (Alto Giro)
    # 30% SKUs = Classe B (Médio Giro)
    # 50% SKUs = Classe C (Baixo Giro)
    
    # Categorias de Produtos de Limpeza
    cleaning_categories = [
        {'name': 'Detergente Líquido', 'weight_range': (0.5, 0.6), 'units_pallet_range': (100, 150)}, # Cx c/ 12 ou 24 un
        {'name': 'Sabão em Pó', 'weight_range': (1.0, 5.0), 'units_pallet_range': (40, 80)}, # Cx maiores
        {'name': 'Desinfetante', 'weight_range': (1.0, 2.0), 'units_pallet_range': (60, 100)},
        {'name': 'Amaciante', 'weight_range': (2.0, 5.0), 'units_pallet_range': (40, 70)},
        {'name': 'Limpador Multiuso', 'weight_range': (0.5, 1.0), 'units_pallet_range': (80, 120)},
        {'name': 'Água Sanitária', 'weight_range': (1.0, 5.0), 'units_pallet_range': (50, 90)}
    ]
    
    for i in range(1, num_skus + 1):
        sku_id = f"SKU_{i:03d}"
        
        # Determinar Classe ABC
        rand_val = random.random()
        if rand_val < 0.2:
            abc_class = 'A'
            popularity_score = random.uniform(50, 100) # Alta popularidade
        elif rand_val < 0.5:
            abc_class = 'B'
            popularity_score = random.uniform(10, 50)
        else:
            abc_class = 'C'
            popularity_score = random.uniform(1, 10)
            
        # Selecionar Categoria e Propriedades Físicas
        cat_data = random.choice(cleaning_categories)
        category = cat_data['name']
        
        # Peso da CAIXA (Picking Unit)
        weight_per_unit = random.uniform(*cat_data['weight_range'])
        
        # Quantidade de Caixas por Palete (Entrada/Armazenagem)
        units_per_pallet = random.randint(*cat_data['units_pallet_range'])
            
        pallet_weight = weight_per_unit * units_per_pallet
        
        skus.append({
            'sku_id': sku_id,
            'abc_class': abc_class,
            'popularity_score': popularity_score,
            'weight_per_unit_kg': round(weight_per_unit, 2),
            'units_per_pallet': units_per_pallet,
            'pallet_weight_kg': round(pallet_weight, 2),
            'description': category, # Usar categoria como descrição
            'category': category
        })
    return pd.DataFrame(skus)

def generate_orders(df_skus, num_orders=2000, demand_multiplier=1.0):
    orders = []
    waves = ['Morning', 'Afternoon']
    
    # Converter para lista com pesos de probabilidade baseados na popularidade
    skus_list = df_skus.to_dict('records')
    weights = [sku['popularity_score'] for sku in skus_list]
    
    # Capacidade do Caminhão (Pallets)
    MAX_PALLETS_PER_TRUCK = 30
    
    for i in range(1, num_orders + 1):
        order_id = f"ORD_{i:05d}"
        day = random.randint(1, 30)
        wave = random.choice(waves)
        
        current_pallets = 0
        
        # Tentar encher o caminhão (ou fazer um pedido LTL)
        # Limite de tentativas para não ficar loop infinito se só tiver itens gigantes
        while current_pallets < MAX_PALLETS_PER_TRUCK:
            # Selecionar SKU
            sku = random.choices(skus_list, weights=weights, k=1)[0]
            
            # Verificar se SKU já está no pedido (simplificação: permite duplicar linha ou não? 
            # Melhor não duplicar SKU no mesmo pedido para simplificar visualização)
            if any(o['sku_id'] == sku['sku_id'] for o in orders if o['order_id'] == order_id):
                continue

            # Definir quantidade (1 a 5 pallets por item, ou fração)
            # Agora geramos baseado em pallets para controlar a capacidade
            pallets_for_item = random.uniform(0.5, 5.0) 
            
            # Ajustar se passar do limite do caminhão
            if current_pallets + pallets_for_item > MAX_PALLETS_PER_TRUCK:
                pallets_for_item = MAX_PALLETS_PER_TRUCK - current_pallets
            
            # Se o pedaço for muito pequeno (ex: < 0.1 pallet), fecha o pedido
            if pallets_for_item < 0.1:
                break
                
            qty = int(pallets_for_item * sku['units_per_pallet'] * demand_multiplier)
            if qty < 1: qty = 1
            
            # Atualizar contagem
            current_pallets += (qty / sku['units_per_pallet'])
            
            orders.append({
                'order_id': order_id,
                'day': day,
                'shipping_wave': wave,
                'sku_id': sku['sku_id'],
                'quantity': qty
            })
            
            # Chance de parar antes de encher (pedidos menores/LTL)
            # 10% de chance de parar a cada item adicionado
            if random.random() < 0.1 and current_pallets > 5:
                break
                
    return pd.DataFrame(orders)