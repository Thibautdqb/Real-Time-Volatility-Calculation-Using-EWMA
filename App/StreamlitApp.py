import websocket
import json
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import ssl
 # Importer les clés depuis config.py
import time
import pandas as pd
from arch import arch_model
import numpy as np
import time
import streamlit as st 
import matplotlib.pyplot as plt
import plotly.graph_objs as go





# Configuration de la page Streamlit
st.set_page_config(
    page_title="Volatility Analysis Multi-Assets",  # Titre de la page
    page_icon="📊",  # Icône de la page (emoji ou fichier image)
    layout="wide",  # Largeur de la page ('centered' ou 'wide')
    initial_sidebar_state="expanded",  # État initial de la barre latérale ('collapsed' ou 'expanded')
    menu_items={
        'Get Help': 'https://www.example.com/help',  # Lien vers la page d'aide
        'Report a bug': 'https://www.example.com/bug',  # Lien vers la page de rapport de bug
        'About': "# Analyse en temps réel de la volatilité de plusieurs actifs\nCette application analyse la volatilité de plusieurs actifs en temps réel à l'aide du modèle EWMA."  # Texte pour la section "À propos"
    }
)

# Barre latérale pour la sélection du stock/actif
st.sidebar.title("Volatility Analysis Settings")

# Sélection de plusieurs actifs pour comparaison
product_type = st.sidebar.selectbox(
    "Choose the type of financial product:",
    ["Cryptos", "Commodities", "Stocks", "ETFs", "Forex", "Volatility Index"]
)

if product_type == "Cryptos":
    selected_assets = st.sidebar.multiselect(
        "Choose the cryptocurrencies:",
        ["BTC-PERPETUAL", "ETH-PERPETUAL", "BTC-USD", "ETH-USD"]
    )
elif product_type == "Commodities":
    selected_assets = st.sidebar.multiselect(
        "Choose the commodities:",
        ["GOLD", "SILVER", "OIL"]
    )
elif product_type == "Stocks":
    selected_assets = st.sidebar.multiselect(
        "Choose the stocks:",
        ["AAPL", "GOOG", "AMZN", "MSFT", "TSLA", "NFLX", "FB"]
    )
elif product_type == "ETFs":
    selected_assets = st.sidebar.multiselect(
        "Choose the ETFs:",
        ["SPY", "DIA", "QQQ"]
    )
elif product_type == "Forex":
    selected_assets = st.sidebar.multiselect(
        "Choose the forex pairs:",
        ["EURUSD", "GBPUSD", "USDJPY"]
    )
elif product_type == "Volatility Index":
    selected_assets = st.sidebar.multiselect(
        "Choose the volatility index:",
        ["VIX"]
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

progress_bar = st.progress(0)

# URL du WebSocket Deribit (environnement de test ou production)
DERIBIT_WS_URL = "wss://test.deribit.com/ws/api/v2"  # Remplacer par 'wss://www.deribit.com/ws/api/v2' pour la production

# Variables pour stocker les données par actif
subscribed_channels = set()
data_list = {asset: [] for asset in selected_assets}  # Un dictionnaire pour stocker les données de chaque actif
volatility_data = {asset: [] for asset in selected_assets}  # Un dictionnaire pour stocker la volatilité de chaque actif

collecte_terminee = False  # Variable pour suivre l'état de la collecte
last_volatility_calc_time = time.time() - 3 
progress_bar = st.progress(0)  # Valeur initiale de 0%
volatility_data = []




# Fonction pour mettre à jour le graphique dans Streamlit
# Fonction pour mettre à jour le graphique dans Streamlit
def update_chart():
    if any(len(volatility_data[asset]) > 0 for asset in selected_assets):
        fig = go.Figure()

        for asset in selected_assets:
            df = pd.DataFrame(volatility_data[asset])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')
            fig.add_trace(go.Scatter(x=df['timestamp'], y=df['volatility'], mode='lines', name=f'Volatility (EWMA) - {asset}'))

        fig.update_layout(
            title="Estimated volatility (EWMA) in real time",
            xaxis_title="Time",
            yaxis_title="Volatility",
            template="plotly_dark"
        )

        chart_placeholder.plotly_chart(fig)






# Fonction pour appliquer le modèle EWMA
def appliquer_modele_ewma(asset, data, lambda_factor=0.10):
    global volatility_data

    prices = pd.Series([item['mark_price'] for item in data])

    if len(prices) < 100:
        return None

    returns = np.log(prices / prices.shift(1)).dropna()

    if returns.var() == 0:
        return None

    variance = returns.var()

    for r in returns:
        variance = lambda_factor * variance + (1 - lambda_factor) * (r ** 2)

    volatility = np.sqrt(variance)

    timestamp = time.time()
    volatility_data[asset].append({'timestamp': timestamp, 'volatility': volatility})

    if len(volatility_data[asset]) >= 100:
        envoyer_email_rapport_volatilites(asset, volatility_data[asset])        
        volatility_data[asset].clear()
    return volatility



def envoyer_email_rapport_volatilites(volatility_data):
    """
    Envoie un email contenant les 100 derniers indices de volatilité avec leur timestamp.
    """
    # Détails de l'email
    email_expediteur = st.secrets["email_credentials"]["FROMEMAIL"]
    mot_de_passe = st.secrets["email_credentials"]["EMAILPASSWORD"]
    destinataire_email = to_email
    serveur_smtp = "smtp.gmail.com"  # Remplace par le serveur SMTP approprié
    port_smtp = 587  # Port SMTP (587 pour TLS, ou 465 pour SSL)

    # Création du message email
    msg = MIMEMultipart("alternative")
    msg['From'] = email_expediteur
    msg['To'] = destinataire_email
    msg['Subject'] = "Rapport des 100 derniers indices de volatilité - Modèle EWMA"

    # Créer le corps du message avec un style HTML
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
    
    # Remplir le tableau avec les données de volatilité
    for entry in volatility_data:
        time_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(entry['timestamp']))
        volatilite_str = f"{entry['volatility']:.6f}"
        message_html += f"""
                    <tr>
                        <td>{time_str}</td>
                        <td>{volatilite_str}</td>
                    </tr>
        """
    
    # Fermer le tableau et l'email HTML
    message_html += """
                </tbody>
            </table>
            <p>Merci et à bientôt,</p>
            <p><em>Équipe d'analyse des données financières</em></p>
        </body>
    </html>
    """
    
    # Attacher le contenu HTML au message
    msg.attach(MIMEText(message_html, "html"))

    # Connexion au serveur SMTP et envoi de l'email
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
    global data_list, collecte_terminee, subscribed_channels, last_volatility_calc_time

    response = json.loads(message)
    print("Message reçu :")
    print(json.dumps(response, indent=4))

    # Si l'authentification est réussie, souscrire aux canaux de prix en temps réel une seule fois
    if 'result' in response and 'id' in response and response['id'] == 9929:
        print("Authentification réussie, souscription aux canaux...")

        # Souscription aux canaux des actifs sélectionnés
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

    # Gestion des données de prix reçues (pour traiter les messages de données)
    if 'params' in response and 'data' in response['params']:
        data = response['params']['data']
        for asset in selected_assets:
            if 'mark_price' in data:
                data_list[asset].append({
                    'timestamp': time.time(),
                    'mark_price': data['mark_price']
                })

                # Limiter la taille de la fenêtre de données
                if len(data_list[asset]) > data_window:
                    data_list[asset].pop(0)

                # Calculer la volatilité et mettre à jour le graphique si l'intervalle est atteint
                if time.time() - last_volatility_calc_time >= time_between_predictions:
                    appliquer_modele_ewma(asset, data_list[asset])
                    update_chart()
                    last_volatility_calc_time = time.time()







# Fonction appelée lorsqu'une erreur se produit
def on_error(ws, error):
    print("Erreur : ", error)

    # Gestion de l'erreur too_many_requests
    if "too_many_requests" in str(error):
        print("Trop de requêtes envoyées. Attente de 5 secondes avant de réessayer...")
        time.sleep(5)  # Attente de 5 secondes avant de réessayer


# Fonction appelée à la fermeture de la connexion WebSocket
def on_close(ws, close_status_code, close_msg):
    print(f"Connexion fermée : Code {close_status_code}, Message : {close_msg}")
    print("Tentative de reconnexion dans 5 secondes...")
    time.sleep(5)
    ws.run_forever()


if __name__ == "__main__":
    # Création de l'instance WebSocketApp et passage des callbacks
    ws = websocket.WebSocketApp(DERIBIT_WS_URL,
                                on_open=on_open,
                                on_message=on_message,
                                on_close=on_close,
                                on_error=on_error)

    # Exécution en mode "forever"
    ws.run_forever()
