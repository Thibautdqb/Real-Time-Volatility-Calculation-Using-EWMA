import websocket
import json
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import ssl
import time
import pandas as pd
from arch import arch_model
import numpy as np
import streamlit as st 
import matplotlib.pyplot as plt
import plotly.graph_objs as go
import requests




# Configuration de la page Streamlit
st.set_page_config(
    page_title="Volatility Analysis Multi-Assets",  
    page_icon="📊",  
    layout="wide",  
    initial_sidebar_state="expanded",  
    menu_items={
        'Get Help': 'https://www.example.com/help',  
        'Report a bug': 'https://www.example.com/bug',  
        'About': "# Analyse en temps réel de la volatilité de plusieurs actifs\nCette application analyse la volatilité de plusieurs actifs en temps réel à l'aide du modèle EWMA."
    }
)
# Initialisation de `st.session_state` pour stocker les données
if "volatility_data" not in st.session_state:
    st.session_state.volatility_data = {}
if "data_list" not in st.session_state:
    st.session_state.data_list = {}

# Barre latérale pour la sélection du stock/actif
st.sidebar.title("Volatility Analysis Settings")

# Sélection de plusieurs actifs pour comparaison

selected_assets = st.sidebar.multiselect(
        "Choose the cryptocurrencies:",
        ["BTC-PERPETUAL", "ETH-PERPETUAL", "SOL-PERPETUAL", "ADA-PERPETUAL", "AVAX-PERPETUAL", "LTC-PERPETUAL"]
    )



# Champs de saisie pour l'email, la fenêtre de données, et l'intervalle de prédiction dans la sidebar
to_email = st.sidebar.text_input("Enter your email address to receive reports:")
data_window = st.sidebar.number_input("Enter the data window size (number of data points):", min_value=50, max_value=500, value=100, step=10)
time_between_predictions = st.sidebar.number_input("Time interval between predictions (in seconds):", min_value=0.1, max_value=60.0, value=10.0, step=0.1)

# Titre et description de l'application
st.title(f"Real-time volatility (EWMA) for selected assets")
st.write(f"This Streamlit application enables you to track the volatility of multiple assets in real time, calculated instantly from market data transmitted via WebSocket. An interactive graph continuously illustrates changes in the volatility of these assets. When 100 real-time estimates are collected, a full report is automatically sent by e-mail.")

# Placeholder pour le graphique
chart_placeholder = st.empty()

if not to_email:
    st.warning("Please enter your email address to receive the volatility reports.")
    st.stop()
chart_placeholder = st.container()
status_placeholder = st.container()
progress_bar = st.progress(0)



# URL du WebSocket Deribit (environnement de test ou production)
DERIBIT_WS_URL = "wss://test.deribit.com/ws/api/v2"

# Variables pour stocker les données par actif
subscribed_channels = set()
data_list = {asset: [] for asset in selected_assets}  
volatility_data = {asset: [] for asset in selected_assets}  

collecte_terminee = False  
last_volatility_calc_time = time.time() - 3 

status_placeholder = st.container()



with status_placeholder:
    st.subheader("Suivi des données et calculs de volatilité")
    data_status = {asset: st.empty() for asset in selected_assets}

# Fonctions utilitaires
@st.cache_data
def get_cached_volatility_data(asset):
    return st.session_state.volatility_data.get(asset, [])

def update_chart():
    with chart_placeholder:
        fig = go.Figure()
        for asset in selected_assets:
            cached_data = get_cached_volatility_data(asset)
            if len(cached_data) > 0:
                df = pd.DataFrame(cached_data)
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')
                fig.add_trace(go.Scatter(
                    x=df['timestamp'],
                    y=df['volatility'],
                    mode='lines',
                    name=f'Volatility (EWMA) - {asset}'
                ))
        if len(fig.data) > 0:
            fig.update_layout(
                title="Estimated volatility (EWMA) in real time for selected assets",
                xaxis_title="Time",
                yaxis_title="Volatility",
                template="plotly_dark"
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.write("No data available to display for the selected assets.")


def appliquer_modele_ewma(asset, data, lambda_factor=0.94):
    prices = pd.Series([item['mark_price'] for item in data])
    if len(prices) < 100:
        data_status[asset].write(f"{asset} : Données actuelles = {len(prices)}, en attente de 100.")
        return None

    returns = np.log(prices / prices.shift(1)).dropna()
    variance = returns.var()
    for r in returns:
        variance = lambda_factor * variance + (1 - lambda_factor) * (r ** 2)

    volatility = np.sqrt(variance)
    timestamp = time.time()
    if asset not in st.session_state.volatility_data:
        st.session_state.volatility_data[asset] = []
    st.session_state.volatility_data[asset].append({'timestamp': timestamp, 'volatility': volatility})
    data_status[asset].write(f"{asset} : Volatilité actuelle = {volatility:.6f}")
    return volatility



def envoyer_email_rapport_volatilites(volatility_data):
    email_expediteur = st.secrets["email_credentials"]["FROMEMAIL"]
    mot_de_passe = st.secrets["email_credentials"]["EMAILPASSWORD"]
    destinataire_email = to_email
    serveur_smtp = "smtp.gmail.com"
    port_smtp = 587  

    msg = MIMEMultipart("alternative")
    msg['From'] = email_expediteur
    msg['To'] = destinataire_email
    msg['Subject'] = "Rapport des 100 derniers indices de volatilité - Modèle EWMA"

    message_html = """
    <html>
        <body>
            <p>Bonjour,</p>
            <p>Veuillez trouver ci-dessous le rapport des <strong>100 derniers indices de volatilité</strong> générés par le modèle EWMA :</p>
            <table border="1" cellpadding="5" cellspacing="0" style="border-collapse: collapse; width: 100%;">
                <thead>
                    <tr style="background-color: #f2f2f2;">
                        <th style="text-align: left;">Timestamp</th>
                        <th style="text-align: left;">Volatilité</th>
                    </tr>
                </thead>
                <tbody>
    """

    for entry in volatility_data:
        time_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(entry['timestamp']))
        volatilite_str = f"{entry['volatility']:.6f}"
        message_html += f"""
                    <tr>
                        <td>{time_str}</td>
                        <td>{volatilite_str}</td>
                    </tr>
        """

    message_html += """
                </tbody>
            </table>
            <p>Merci et à bientôt,</p>
            <p><em>Équipe d'analyse des données financières</em></p>
        </body>
    </html>
    """

    msg.attach(MIMEText(message_html, "html"))

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(serveur_smtp, port_smtp) as serveur:
            serveur.starttls(context=context)
            serveur.login(email_expediteur, mot_de_passe)
            serveur.sendmail(email_expediteur, destinataire_email, msg.as_string())
            print("Email envoyé avec succès!")
    except Exception as e:
        print(f"Erreur lors de l'envoi de l'email : {e}")


def on_message(ws, message):
    global collecte_terminee, subscribed_channels, last_volatility_calc_time

    response = json.loads(message)
    print("Message reçu :")
    print(json.dumps(response, indent=4))

    # Authentification réussie
    if 'result' in response and 'id' in response and response['id'] == 9929:
        print("Authentification réussie, souscription aux canaux...")

        # Souscription aux canaux pour chaque actif sélectionné
        for asset in selected_assets:
            channel_ticker = f"ticker.{asset}.raw"
            if channel_ticker not in subscribed_channels:
                subscribe_message = {
                    "jsonrpc": "2.0",
                    "method": "public/subscribe",
                    "params": {
                        "channels": [channel_ticker]
                    },
                    "id": 43
                }
                ws.send(json.dumps(subscribe_message))
                subscribed_channels.add(channel_ticker)
                print(f"Souscrit au canal {channel_ticker}")

    # Vérification de la réception des données
    if 'params' in response and 'data' in response['params']:
        data = response['params']['data']

        # Affichage des données reçues pour chaque actif, si elles contiennent mark_price
        if 'mark_price' in data:
            asset = response['params']['channel'].split('.')[1]  # Extraction de l'actif du nom du canal
            if asset in selected_assets:
                print(f"Données de prix reçues pour {asset}: {data['mark_price']}")

                # Récupérer les données mises en cache pour cet actif
                cached_data = get_cached_data_list(asset)

                # Ajout des nouvelles données de prix
                cached_data.append({
                    'timestamp': time.time(),
                    'mark_price': data['mark_price']
                })
                print(f"Données ajoutées pour {asset} : {cached_data[-1]}")

                # Limite de la fenêtre de données pour l'actif (éviter les débordements)
                if len(cached_data) > data_window:
                    cached_data.pop(0)

                # Mettre à jour les données dans `st.session_state`
                st.session_state.data_list[asset] = cached_data

                # Vérification de l'intervalle de temps entre les prédictions
                if time.time() - last_volatility_calc_time >= time_between_predictions:
                    # Appliquer le modèle EWMA à l'actif avec les données collectées
                    appliquer_modele_ewma(asset, cached_data)
                    # Mettre à jour le graphique après le calcul de la volatilité
                    update_chart()
                    # Mettre à jour le temps de la dernière prédiction
                    last_volatility_calc_time = time.time()
            else:
                print(f"Aucun traitement prévu pour cet actif : {asset}")
        else:
            print("Données reçues sans prix de marché (mark_price). Ignorées.")


def on_open(ws):
    print("Connexion ouverte")

    auth_message = {
        "jsonrpc": "2.0",
        "id": 9929,
        "method": "public/auth",
        "params": {
            "grant_type": "client_credentials",  
            "client_id": st.secrets["api_credentials"]["API_KEY"],
            "client_secret": st.secrets["api_credentials"]["API_SECRET"]
        }
    }
    ws.send(json.dumps(auth_message))
    print("Message d'authentification envoyé")


def on_error(ws, error):
    print("Erreur : ", error)

    if "too_many_requests" in str(error):
        print("Trop de requêtes envoyées. Attente de 5 secondes avant de réessayer...")
        time.sleep(5)


# Limite les tentatives de reconnexion
reconnection_attempts = 0

def on_close(ws, close_status_code, close_msg):
    global reconnection_attempts
    print(f"Connexion fermée : Code {close_status_code}, Message : {close_msg}")
    if reconnection_attempts < 5:  # Limite à 5 tentatives
        reconnection_attempts += 1
        print("Tentative de reconnexion dans 5 secondes...")
        time.sleep(5)
        ws.run_forever()
    else:
        print("Nombre de tentatives de reconnexion atteint. Veuillez vérifier votre connexion.")



def calculer_volatilite_initiale(asset, historique_data, lambda_factor=0.94):
    global volatility_data

    if len(historique_data) < 2:  # Vérifiez qu'il y a au moins 2 points pour calculer les rendements
        st.warning(f"Pas assez de données historiques pour {asset}.")
        return

    prices = pd.Series([item['mark_price'] for item in historique_data])
    returns = np.log(prices / prices.shift(1)).dropna()  # Rendements log
    variance = returns.var()

    volatility_points = []  # Liste temporaire pour stocker les points calculés
    for i, r in enumerate(returns):
        variance = lambda_factor * variance + (1 - lambda_factor) * (r ** 2)
        volatility = np.sqrt(variance)

        # Stocker chaque volatilité calculée
        volatility_points.append({
            'timestamp': historique_data[i + 1]['timestamp'],  # Décalage pour aligner avec returns
            'volatility': volatility
        })

    # Ajouter toutes les données calculées au stockage global
    volatility_data[asset].extend(volatility_points)

    st.write(f"Volatilité initiale calculée pour {asset}. Points calculés : {len(volatility_points)}.")


def charger_donnees_tick_deribit(asset):
    """
    Cette fonction récupère des données de l'heure précédente pour un actif donné via l'API de Deribit.
    """
    url = "https://www.deribit.com/api/v2/public/get_tradingview_chart_data"
    
    # Calcul des timestamps pour l'heure précédente
    end_timestamp = int(time.time() * 1000)  # Timestamp actuel en millisecondes
    start_timestamp = end_timestamp - 3600000  # Une heure avant en millisecondes

    params = {
        "instrument_name": asset,
        "resolution": "1",  # Utiliser une résolution fine (1 minute)
        "start_timestamp": start_timestamp,
        "end_timestamp": end_timestamp
    }
    
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()  # vérifie si la requête a échoué
        data = response.json()
        
        # Vérifie si le résultat est valide et contient les clés nécessaires
        if "result" in data and all(key in data["result"] for key in ["ticks", "close"]):
            historique_data = [{'timestamp': ts / 1000, 'mark_price': close} 
                               for ts, close in zip(data["result"]["ticks"], data["result"]["close"])]
            
            # Convertir les données en DataFrame pour un affichage plus lisible
            df = pd.DataFrame(historique_data)
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')
            
            # Afficher le titre et les DataFrames côte à côte avec une seule paire de colonnes
            st.title(f"Datasets des données historiques pour {asset}")
            col1, col2 = st.columns(2)
            
            with col1:
                st.write("Données brutes")
                st.dataframe(df)
            
            with col2:
                # Exemple : affiche une autre DataFrame (ici on peut utiliser une transformation ou un autre jeu de données)
                df_analyse = df.copy()  # Transformer les données pour l'exemple
                df_analyse['variation'] = df['mark_price'].pct_change() * 100
                st.write("Données avec variation en %")
                st.dataframe(df_analyse)
            
            return historique_data
        else:
            st.warning(f"Les données de l'heure précédente pour {asset} ne sont pas disponibles ou sont incomplètes.")
            return []
    
    except requests.exceptions.RequestException as e:
        st.warning(f"Erreur de connexion pour récupérer les données de {asset}: {e}")
        return []
    except Exception as e:
        st.warning(f"Une erreur inattendue est survenue lors de la récupération des données pour {asset}: {e}")
        return []  



def augmenter_resolution_historique(historique_data, interval_seconds):
    """
    Augmente la résolution des données historiques pour correspondre à l'intervalle défini par l'utilisateur.

    :param historique_data: Liste de dicts contenant des timestamps et des prix.
    :param interval_seconds: Intervalle cible en secondes.
    :return: Nouvelle liste interpolée.
    """
    # Convertir les données historiques en DataFrame
    df = pd.DataFrame(historique_data)
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')  # Convertir en datetime
    df.set_index('timestamp', inplace=True)

    # Générer une grille temporelle plus dense à l'intervalle désiré
    new_index = pd.date_range(
        start=df.index.min(),
        end=df.index.max(),
        freq=f"{interval_seconds}S"  # Fréquence basée sur l'intervalle utilisateur
    )

    # Appliquer l'interpolation linéaire pour les prix
    df_interpolated = df.reindex(new_index).interpolate(method='linear')

    # Retourner les données au format original (liste de dicts)
    result = [
        {'timestamp': ts.timestamp(), 'mark_price': price}
        for ts, price in zip(df_interpolated.index, df_interpolated['mark_price'])
    ]
    return result



if __name__ == "__main__":
    for asset in selected_assets:
        historique_data = charger_donnees_tick_deribit(asset)
        if historique_data:
            historique_data = augmenter_resolution_historique(historique_data, int(time_between_predictions))
            
            # Afficher les données interpolées pour vérifier
            st.write(f"Données interpolées pour {asset} (intervalle : {time_between_predictions} secondes):")
            st.dataframe(pd.DataFrame(historique_data))
            
            calculer_volatilite_initiale(asset, historique_data)
        else:
            st.warning(f"Pas de données historiques pour l'actif {asset}.")



    
    # Mise à jour du graphique avec les données historiques
    update_chart()  # Affiche le graphique dès le démarrage

    # Lancement de la connexion WebSocket pour la collecte de données en temps réel
    ws = websocket.WebSocketApp(
        DERIBIT_WS_URL,
        on_open=on_open,
        on_message=on_message,
        on_close=on_close,
        on_error=on_error
    )
    ws.run_forever()

