import streamlit as st
import pandas as pd
import folium
from folium.plugins import MarkerCluster
from ortools.constraint_solver import pywrapcp
from ortools.constraint_solver import routing_enums_pb2
from streamlit_folium import st_folium

# Cargar los datos
data = pd.read_excel('clientes_dias_sin_rechazo_completo.xlsx')

# Configurar la aplicación Streamlit
st.title("Optimización de Ruta de Vendedores")

# Entradas del usuario
codigo_vendedor = st.text_input("Ingrese el código del vendedor")
latitud_vendedor = st.number_input("Ingrese la latitud actual del vendedor", format="%.6f")
longitud_vendedor = st.number_input("Ingrese la longitud actual del vendedor", format="%.6f")
fecha = st.date_input("Seleccione la fecha")
distritos = data['Distrito'].unique()
distrito_seleccionado = st.selectbox("Seleccione el distrito", distritos)

if st.button("Optimizar Ruta"):
    # Convertir la fecha a día de la semana
    dia_seleccionado = fecha.strftime("%A")

    # Filtrar clientes por el vendedor, el día seleccionado y el distrito
    clientes_vendedor = data[(data['Codigo_Vendedor'] == codigo_vendedor) &
                             (data['Distrito'] == distrito_seleccionado) &
                             (data['Dias_Sin_Rechazo'].apply(lambda x: dia_seleccionado in x if pd.notna(x) else False))]

    if clientes_vendedor.empty:
        st.warning("No se encontraron clientes para el vendedor, distrito y día seleccionados.")
    else:
        # Obtener coordenadas de los clientes
        coordenadas = clientes_vendedor[['Codigo_Cliente', 'Nombre_Cliente', 'LATITUD', 'LONGITUD']]

        # Agregar la ubicación del vendedor al inicio de las coordenadas
        coordenadas_vendedor = pd.DataFrame({
            'Codigo_Cliente': [codigo_vendedor],
            'Nombre_Cliente': ['Vendedor'],
            'LATITUD': [latitud_vendedor],
            'LONGITUD': [longitud_vendedor]
        })
        coordenadas = pd.concat([coordenadas_vendedor, coordenadas], ignore_index=True)

        # Mostrar los clientes en el mapa
        st.subheader("Mapa de Clientes")
        mapa = folium.Map(location=[latitud_vendedor, longitud_vendedor], zoom_start=12)
        marker_cluster = MarkerCluster().add_to(mapa)

        for idx, row in coordenadas.iterrows():
            if row['Nombre_Cliente'] == 'Vendedor':
                folium.Marker(location=[row['LATITUD'], row['LONGITUD']], 
                              popup=row['Codigo_Cliente'], 
                              icon=folium.Icon(color='white', icon='info-sign')).add_to(marker_cluster)
            else:
                folium.Marker(location=[row['LATITUD'], row['LONGITUD']], 
                              popup=f"{row['Codigo_Cliente']} - {row['Nombre_Cliente']}",
                              icon=folium.Icon(color='red', icon='info-sign')).add_to(marker_cluster)

        st_folium(mapa, width=700, height=500)

        # Optimización de Ruta
        def create_data_model():
            data = {}
            data['locations'] = coordenadas[['LATITUD', 'LONGITUD']].values.tolist()
            data['num_vehicles'] = 1
            data['depot'] = 0
            return data

        def compute_euclidean_distance_matrix(locations):
            distances = []
            for from_node in locations:
                row = []
                for to_node in locations:
                    row.append(((from_node[0] - to_node[0])**2 + (from_node[1] - to_node[1])**2)**0.5)
                distances.append(row)
            return distances

        # Crear modelo de datos
        data_model = create_data_model()
        distance_matrix = compute_euclidean_distance_matrix(data_model['locations'])

        # Crear el gestor de rutas
        manager = pywrapcp.RoutingIndexManager(len(data_model['locations']), 
                                               data_model['num_vehicles'], 
                                               data_model['depot'])
        routing = pywrapcp.RoutingModel(manager)

        def distance_callback(from_index, to_index):
            from_node = manager.IndexToNode(from_index)
            to_node = manager.IndexToNode(to_index)
            return distance_matrix[from_node][to_node]

        transit_callback_index = routing.RegisterTransitCallback(distance_callback)
        routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

        # Parámetros de búsqueda
        search_parameters = pywrapcp.DefaultRoutingSearchParameters()
        search_parameters.first_solution_strategy = (routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC)

        # Resolver el problema
        solution = routing.SolveWithParameters(search_parameters)

        # Obtener la ruta y mostrarla en el mapa
        if solution:
            st.subheader("Ruta Optimizada")
            index = routing.Start(0)
            plan_output = 'Ruta:\n'
            route = []
            step = 1
            while not routing.IsEnd(index):
                node_index = manager.IndexToNode(index)
                route.append(node_index)
                plan_output += f"({step}) {coordenadas.iloc[node_index]['Codigo_Cliente']} - {coordenadas.iloc[node_index]['Nombre_Cliente']}\n"
                index = solution.Value(routing.NextVar(index))
                step += 1
            st.text(plan_output)
            
            # Mostrar la ruta en el mapa
            ruta_mapa = folium.Map(location=[latitud_vendedor, longitud_vendedor], zoom_start=12)
            for i in range(len(route) - 1):
                folium.Marker(location=data_model['locations'][route[i]], 
                              popup=f"({i+1}) {coordenadas.iloc[route[i]]['Codigo_Cliente']} - {coordenadas.iloc[route[i]]['Nombre_Cliente']}",
                              icon=folium.Icon(color='red' if i != 0 else 'white', icon='info-sign')).add_to(ruta_mapa)
                folium.PolyLine(locations=[data_model['locations'][route[i]], 
                                           data_model['locations'][route[i+1]]], color='blue').add_to(ruta_mapa)
            st_folium(ruta_mapa, width=700, height=500)
        else:
            st.error("No se pudo encontrar una solución de ruta.")