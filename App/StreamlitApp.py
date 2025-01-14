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
# Initialisation de st.session_state pour stocker les données
if "volatility_data" not in st.session_state:
    st.session_state.volatility_data = {}
if "data_list" not in st.session_state:
    st.session_state.data_list = {}
if "chart_fig" not in st.session_state:
    st.session_state.chart_fig = go.Figure()
if "last_chart_update" not in st.session_state:
    st.session_state.last_chart_update = 0
    
# Barre latérale pour la sélection du stock/actif
st.sidebar.title("Volatility Analysis Settings")

# Sélection de plusieurs actifs pour comparaison

selected_assets = st.sidebar.multiselect(
        "Choose the cryptocurrencies:",
        ["BTC-PERPETUAL", "ETH-PERPETUAL", "SOL-PERPETUAL", "ADA-PERPETUAL", "AVAX-PERPETUAL"]
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

# Placeholder pour le statut des données
status_placeholder = st.container()
with status_placeholder:
    st.subheader("Data and Volatility Status")
    data_status = {asset: st.empty() for asset in selected_assets}

if not to_email:
    st.warning("Please enter your email address to receive the volatility reports.")
    st.stop()
status_placeholder = st.container()
progress_bar = st.progress(0)


# URL du WebSocket Deribit (environnement de test ou production)
DERIBIT_WS_URL = "wss://test.deribit.com/ws/api/v2"

# Variables pour stocker les données par actif
subscribed_channels = set()

collecte_terminee = False  
last_volatility_calc_time = time.time() - 3 
# Initialisation des espaces dans st.session_state si non définis
# Initialisation des espaces dans st.session_state si non définis
if "data_list" not in st.session_state:
    st.session_state.data_list = {asset: [] for asset in selected_assets}
if "volatility_data" not in st.session_state:
    st.session_state.volatility_data = {asset: [] for asset in selected_assets}




def reset_session_state():
    if "volatility_data" not in st.session_state:
        st.session_state.volatility_data = {asset: [] for asset in selected_assets}
    if "data_list" not in st.session_state:
        st.session_state.data_list = {asset: [] for asset in selected_assets}

# Initialisation des espaces dans st.session_state au démarrage
if "app_initialized" not in st.session_state:
    # Réinitialisation des données
    reset_session_state()
    # Marquer l'application comme initialisée
    st.session_state.app_initialized = True



# Fonction utilitaire pour récupérer les données de volatilité en cache
def get_cached_volatility_data(asset):
    """Récupère ou initialise les données de volatilité pour un actif donné."""
    if asset not in st.session_state.volatility_data:
        st.session_state.volatility_data[asset] = []
    return st.session_state.volatility_data[asset]


# Fonction utilitaire pour récupérer ou initialiser les fenêtres de prix
def get_cached_price_data(asset):
    """Récupère ou initialise les données de prix pour un actif donné."""
    if asset not in st.session_state.data_list:
        st.session_state.data_list[asset] = []
    return st.session_state.data_list[asset]

# Fonction pour mettre à jour le graphique
def update_chart():
    """
    Met à jour le graphique en ajoutant les nouvelles données sans créer de doublons.
    Cette version utilise un index pour les traces et optimise les mises à jour incrémentielles.
    """
    current_time = time.time()

    # Respecter l'intervalle minimal entre les mises à jour
    if current_time - st.session_state["last_chart_update"] < time_between_predictions:
        return

    fig = st.session_state["chart_fig"]

    # Créer un index des noms des traces existantes pour des recherches rapides
    existing_traces = {trace.name: i for i, trace in enumerate(fig.data)}
    updated = False  # Indicateur de modification

    for asset in selected_assets:
        # Récupérer les données de volatilité en cache pour l'actif
        cached_volatility = get_cached_volatility_data(asset)

        if len(cached_volatility) > 0:
            # Convertir les données en DataFrame pour le traitement
            df = pd.DataFrame(cached_volatility)
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')
            trace_name = f'Volatility (EWMA) - {asset}'

            if trace_name in existing_traces:
                # Mise à jour de la trace existante
                trace_index = existing_traces[trace_name]
                fig.data[trace_index].x = df['timestamp']
                fig.data[trace_index].y = df['volatility']
            else:
                # Ajout d'une nouvelle trace si elle n'existe pas
                fig.add_trace(go.Scatter(
                    x=df['timestamp'],
                    y=df['volatility'],
                    mode='lines',
                    name=trace_name
                ))
            updated = True

    # Appliquer les mises à jour si le graphique a été modifié
    if updated:
        fig.update_layout(
            title="Estimated volatility (EWMA) in real time for selected assets",
            xaxis_title="Time",
            yaxis_title="Volatility",
            template="plotly_dark"
        )
        st.session_state["chart_fig"] = fig  # Sauvegarder le graphique mis à jour dans st.session_state
        chart_placeholder.plotly_chart(fig, use_container_width=True)
        st.session_state["last_chart_update"] = current_time



def appliquer_modele_ewma(asset, price_data, lambda_factor=0.94):
    prices = pd.Series([item['mark_price'] for item in price_data])
    if len(prices) < 2:
        return None
    returns = np.log(prices / prices.shift(1)).dropna()

    # Démarrage avec la dernière variance stockée
    variance = st.session_state.get(f"{asset}_last_variance", returns.var())
    for r in returns:
        variance = lambda_factor * variance + (1 - lambda_factor) * r ** 2
    st.session_state[f"{asset}_last_variance"] = variance  # Sauvegarde
    volatility = np.sqrt(variance)
    timestamp = time.time()
    get_cached_volatility_data(asset).append({'timestamp': timestamp, 'volatility': volatility})
    return volatility

def on_message(ws, message):
    """Gère les messages reçus via WebSocket et traite les données en temps réel."""
    global last_volatility_calc_time

    # Charger la réponse JSON
    response = json.loads(message)

    # Log : Réponse brute reçue
    print(f"Message reçu : {json.dumps(response, indent=4)}")

    # Gestion des messages d'authentification
    if 'id' in response and 'result' in response:
        print("Message d'authentification reçu ou autre réponse.")
        if response['id'] == 9929:  # ID correspondant à l'authentification
            print("Authentification réussie.")
        return  # Ne rien faire d'autre avec ces messages

    # Vérifier si les données contiennent des informations pertinentes
    if 'params' in response and 'data' in response['params']:
        data = response['params']['data']

        # Vérifier que les données contiennent un prix marqué
        if 'mark_price' in data:
            asset = response['params']['channel'].split('.')[1]  # Extraction de l'actif
            print(f"Asset détecté : {asset}")

            if asset in selected_assets:
                # Récupérer ou initialiser les données de prix pour cet actif
                cached_prices = get_cached_price_data(asset)

                # Ajouter les nouvelles données de prix avec un timestamp
                cached_prices.append({
                    'timestamp': time.time(),
                    'mark_price': data['mark_price']
                })

                # Log : Données ajoutées
                print(f"Nouvelles données de prix ajoutées pour {asset}: {cached_prices[-1]}")

                # Limiter la taille de la fenêtre de données
                if len(cached_prices) > data_window:
                    removed = cached_prices.pop(0)
                    
                    print(f"Donnée supprimée pour {asset} (fenêtre limitée à {data_window}): {removed}")
                # Mettre à jour `st.session_state`
                st.session_state.data_list[asset] = cached_prices

                # Log : Longueur actuelle des données de prix
                print(f"Longueur des données de prix pour {asset}: {len(cached_prices)}")

                # Vérifier si le temps écoulé permet un nouveau calcul de volatilité
                current_time = time.time()
                time_since_last_calc = current_time - last_volatility_calc_time
                print(f"Temps depuis le dernier calcul de volatilité : {time_since_last_calc:.2f} secondes")

                if time_since_last_calc >= time_between_predictions:
                    print(f"Calcul de la volatilité pour {asset} en cours...")

                    # Calculer la volatilité en utilisant le modèle EWMA
                    new_volatility = appliquer_modele_ewma(asset, cached_prices)

                    if new_volatility is not None:
                        print(f"Nouvelle volatilité calculée pour {asset}: {new_volatility}")

                    # Mettre à jour le graphique
                    update_chart()

                    # Mettre à jour le temps du dernier calcul
                    last_volatility_calc_time = current_time
                else:
                    print(f"Aucun calcul effectué pour {asset} (attente du prochain intervalle).")
            else:
                print(f"L'actif {asset} n'est pas sélectionné pour l'analyse.")
        else:
            print("Aucun prix marqué trouvé dans les données reçues. Ignoré.")
    else:
        print("Structure de données inattendue dans le message. Ignoré.")






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




def on_open(ws):
    """Gestion de l'ouverture de la connexion WebSocket."""
    print("Connexion ouverte")

    # Authentification
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

    # Souscription unique aux actifs sélectionnés
    for asset in selected_assets:
        channel_ticker = f"ticker.{asset}.raw"
        if channel_ticker not in subscribed_channels:
            subscribe_message = {
                "jsonrpc": "2.0",
                "method": "public/subscribe",
                "params": {"channels": [channel_ticker]},
                "id": 43
            }
            ws.send(json.dumps(subscribe_message))
            subscribed_channels.add(channel_ticker)
            print(f"Souscrit au canal {channel_ticker}")


def on_error(ws, error):
    """Gestion des erreurs de la connexion WebSocket."""
    print("Erreur : ", error)

    if "too_many_requests" in str(error):
        print("Trop de requêtes envoyées. Attente prolongée avant de réessayer...")
        time.sleep(30)  # Attendre plus longtemps avant de réessayer
        return



# Limite les tentatives de reconnexion
reconnection_attempts = 0

def on_close(ws, close_status_code, close_msg):
    """Gestion de la fermeture de la connexion WebSocket."""
    global reconnection_attempts
    print(f"Connexion fermée : Code {close_status_code}, Message : {close_msg}")

    if close_status_code == 1000:
        print("Connexion fermée volontairement.")
        return

    if reconnection_attempts < 10:  # Limite des tentatives de reconnexion
        delay = min(2 ** reconnection_attempts, 60)  # Exponential backoff avec un maximum de 60 secondes
        print(f"Tentative de reconnexion dans {delay} secondes...")
        time.sleep(delay)
        reconnection_attempts += 1
        ws.run_forever()
    else:
        print("Nombre maximal de tentatives de reconnexion atteint. Arrêt.")




def calculer_volatilite_initiale(asset, historique_data, lambda_factor=0.94):
    """
    Calcule la volatilité initiale à partir des données historiques et l'enregistre dans st.session_state.
    """
    # Vérifiez qu'il y a au moins 2 points pour calculer les rendements
    if len(historique_data) < 2:
        st.warning(f"Pas assez de données historiques pour {asset}.")
        return

    # Récupérer ou initialiser la liste des volatilités pour l'actif
    if asset not in st.session_state.volatility_data:
        st.session_state.volatility_data[asset] = []

    # Extraire les prix et calculer les rendements log
    prices = pd.Series([item['mark_price'] for item in historique_data])
    returns = np.log(prices / prices.shift(1)).dropna()
    variance = returns.var()

    volatility_points = []  # Liste temporaire pour stocker les points calculés

    # Calculer la volatilité avec EWMA
    for i, r in enumerate(returns):
        variance = lambda_factor * variance + (1 - lambda_factor) * (r ** 2)
        volatility = np.sqrt(variance)

        # Stocker chaque volatilité calculée avec le timestamp correspondant
        volatility_points.append({
            'timestamp': historique_data[i + 1]['timestamp'],  # Décalage pour aligner avec returns
            'volatility': volatility
        })

    # Ajouter les points calculés à st.session_state.volatility_data
    st.session_state.volatility_data[asset].extend(volatility_points)

    # Afficher un message avec le nombre de points calculés
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

def afficher_progression():
    """
    Affiche la progression du remplissage des données pour chaque actif,
    y compris les données de prix et les données de volatilité.
    """
    st.sidebar.title("Progression des données")
    
    # Conteneurs pour chaque actif
    for asset in selected_assets:
        st.subheader(f"Progression pour {asset}")

        # Calcul de la progression des données de prix
        data_points = len(st.session_state.data_list[asset])
        price_progress = data_points / data_window * 100
        st.text(f"Données de prix : {data_points}/{data_window}")
        st.progress(min(int(price_progress), 100))

        # Calcul de la progression des données de volatilité
        volatility_points = len(st.session_state.volatility_data[asset])
        st.text(f"Données de volatilité : {volatility_points} points calculés")
        if volatility_points > 0:
            last_volatility = st.session_state.volatility_data[asset][-1]["volatility"]
            st.metric(label="Dernière volatilité", value=f"{last_volatility:.6f}")
        else:
            st.write("Aucune donnée de volatilité disponible pour l'instant.")


if __name__ == "__main__":
    # Traiter les données historiques pour chaque actif sélectionné
    for asset in selected_assets:
        historique_data = charger_donnees_tick_deribit(asset)
        if historique_data:
            historique_data = augmenter_resolution_historique(historique_data, int(time_between_predictions))
            # Afficher les données interpolées pour vérifier
            st.write(f"Données interpolées pour {asset} (intervalle : {time_between_predictions} secondes):")
            st.dataframe(pd.DataFrame(historique_data))

            # Calculer la volatilité initiale
            calculer_volatilite_initiale(asset, historique_data)
        else:
            st.warning(f"Pas de données historiques pour l'actif {asset}.")
    afficher_progression()

    # Mise à jour du graphique une seule fois après le traitement de toutes les données
    update_chart()  # Affiche le graphique après avoir traité tous les actifs


    # Lancement de la connexion WebSocket pour la collecte de données en temps réel
    ws = websocket.WebSocketApp(
        DERIBIT_WS_URL,
        on_open=on_open,
        on_message=on_message,
        on_close=on_close,
        on_error=on_error
    )
    ws.run_forever()
