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
DERIBIT_WS_URL = "wss://test.deribit.com/ws/api/v2"

# Variables pour stocker les données par actif
subscribed_channels = set()
data_list = {asset: [] for asset in selected_assets}  
volatility_data = {asset: [] for asset in selected_assets}  

collecte_terminee = False  
last_volatility_calc_time = time.time() - 3 


def update_chart():
    # Créer une nouvelle figure pour afficher les actifs sélectionnés
    fig = go.Figure()
    # Parcourir tous les actifs sélectionnés et vérifier qu'ils ont des données à afficher
    for asset in selected_assets:
        if len(volatility_data[asset]) > 0:
            df = pd.DataFrame(volatility_data[asset])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')
            # Ajouter une nouvelle trace pour chaque actif
            fig.add_trace(go.Scatter(
                x=df['timestamp'],
                y=df['volatility'],
                mode='lines',
                name=f'Volatility (EWMA) - {asset}'
            ))
        else:
            # Si pas de données pour cet actif, afficher un avertissement dans la console
            print(f"Aucune donnée disponible pour {asset} à afficher dans le graphique.")
    # Vérification : S'il y a au moins une trace ajoutée au graphique
    if len(fig.data) > 0:
        fig.update_layout(
            title="Estimated volatility (EWMA) in real time for selected assets",
            xaxis_title="Time",
            yaxis_title="Volatility",
            template="plotly_dark"
        )
        chart_placeholder.plotly_chart(fig)
    else:
        # Si aucune donnée n'est disponible, afficher un message dans le placeholder
        chart_placeholder.write("No data available to display for the selected assets.")


def appliquer_modele_ewma(asset, data, lambda_factor=0.10):
    global volatility_data

    prices = pd.Series([item['mark_price'] for item in data])

    if len(prices) < 100:
        st.write(f"Pas assez de données pour calculer la volatilité pour {asset}. Données actuelles : {len(prices)}")
        return None

    returns = np.log(prices / prices.shift(1)).dropna()

    if returns.var() == 0:
        st.write(f"La variance est nulle pour {asset}. Ignoré pour ce calcul.")
        return None

    variance = returns.var()

    for r in returns:
        variance = lambda_factor * variance + (1 - lambda_factor) * (r ** 2)

    volatility = np.sqrt(variance)
    timestamp = time.time()
    # Ajouter la volatilité calculée pour l'actif dans volatility_data
    volatility_data[asset].append({'timestamp': timestamp, 'volatility': volatility})

    # Affichage de la volatilité pour cet actif à cette étape du calcul
    st.write(f"Volatilité calculée pour {asset} : {volatility:.6f} à {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(timestamp))}")
    
    # Vérification du contenu de volatility_data pour chaque actif
    st.write(f"Données de volatilité pour {asset} :", volatility_data[asset])

    if len(volatility_data[asset]) >= 100:
        envoyer_email_rapport_volatilites(volatility_data[asset])        
        st.write(f"Rapport envoyé pour {asset}. Réinitialisation des données.")
        volatility_data[asset].clear()
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
    global data_list, collecte_terminee, subscribed_channels, last_volatility_calc_time

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
    # Traitement des données reçues en temps réel
    if 'params' in response and 'data' in response['params']:
        data = response['params']['data']

        # Gestion des données de prix pour chaque actif sélectionné
         for asset in selected_assets:
            if 'mark_price' in data:
                data_list[asset].append({
                    'timestamp': time.time(),
                    'mark_price': data['mark_price']
                })
                print(f"Données ajoutées pour {asset} : {data_list[asset][-1]}")
    
                # Limiter la taille de la fenêtre de données pour l'actif (éviter les débordements)
                if len(data_list[asset]) > data_window:
                    data_list[asset].pop(0)
    
                # Vérification si l'intervalle de temps entre les prédictions est atteint
                if time.time() - last_volatility_calc_time >= time_between_predictions:
                    # Appliquer le modèle EWMA à l'actif avec les données collectées
                    appliquer_modele_ewma(asset, data_list[asset])
                    # Mettre à jour le graphique après le calcul de la volatilité
                    update_chart()
                    # Mettre à jour le temps de la dernière prédiction
                    last_volatility_calc_time = time.time()


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


def on_close(ws, close_status_code, close_msg):
    print(f"Connexion fermée : Code {close_status_code}, Message : {close_msg}")
    print("Tentative de reconnexion dans 5 secondes...")
    time.sleep(5)
    ws.run_forever()


if __name__ == "__main__":
    ws = websocket.WebSocketApp(DERIBIT_WS_URL,
                                on_open=on_open,
                                on_message=on_message,
                                on_close=on_close,
                                on_error=on_error)
    ws.run_forever()
