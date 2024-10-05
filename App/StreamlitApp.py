import websocket
import json
import os
from config import API_KEY, API_SECRET , TOEMAIL, FROMEMAIL, EMAILPASSWORD
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


st.set_page_config(
    page_title="Analyse de Volatilité BTC-PERPETUAL",  # Titre de la page
    page_icon="📊",  # Icône de la page (emoji ou fichier image)
    layout="wide",  # Largeur de la page ('centered' ou 'wide')
    initial_sidebar_state="expanded",  # État initial de la barre latérale ('collapsed' ou 'expanded')
    menu_items={
        'Get Help': 'https://www.example.com/help',  # Lien vers la page d'aide
        'Report a bug': 'https://www.example.com/bug',  # Lien vers la page de rapport de bug
        'About': "# Analyse en temps réel de la volatilité du contrat BTC-PERPETUAL\nCette application analyse la volatilité du contrat perpétuel Bitcoin en temps réel à l'aide du modèle EWMA."  # Texte pour la section "À propos"
    }
)
st.title("Volatilité en temps réel (EWMA)")

st.write("Cette application Streamlit permet de suivre en temps réel la volatilité du contrat perpétuel BTC-PERPETUAL, calculée instantanément à partir des données de marché transmises via WebSocket. Un graphique interactif illustre en continu l'évolution de la volatilité de cet actif. Lorsque 100 estimations en temps réel sont collectées, un rapport complet est automatiquement envoyé par e-mail.")

chart_placeholder = st.empty()


# URL du WebSocket Deribit (environnement de test ou production)
DERIBIT_WS_URL = "wss://test.deribit.com/ws/api/v2"  # Remplacer par 'wss://www.deribit.com/ws/api/v2' pour la production

# Garde une trace des canaux auxquels tu es abonné
subscribed_channels = set()

# Liste pour stocker les données
data_list = []

collecte_terminee = False  # Variable pour suivre l'état de la collecte
last_volatility_calc_time = time.time() - 3 

progress_bar = st.progress(0)  # Valeur initiale de 0%
volatility_data = []




# Fonction pour mettre à jour le graphique dans Streamlit
# Fonction pour mettre à jour le graphique dans Streamlit
def update_chart():
    global volatility_data

    if len(volatility_data) > 0:
        df = pd.DataFrame(volatility_data)
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')

        # Graphique interactif avec Plotly
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df['timestamp'], y=df['volatility'], mode='lines', name='Volatilité (EWMA)'))
        fig.update_layout(
            title="Volatilité estimée (EWMA) en temps réel",
            xaxis_title="Temps",
            yaxis_title="Volatilité",
            template="plotly_dark"
        )

        chart_placeholder.plotly_chart(fig)


# Fonction appelée à l'ouverture de la connexion WebSocket
def on_open(ws):
    print("Connexion ouverte")

    # Message d'authentification via API
    auth_message = {
        "jsonrpc": "2.0",
        "id": 9929,
        "method": "public/auth",
        "params": {
            "grant_type": "client_credentials",  # Le type de connexion à utiliser
            "client_id": API_KEY,
            "client_secret": API_SECRET
        }
    }

    ws.send(json.dumps(auth_message))
    print("Message d'authentification envoyé")




def appliquer_modele_ewma(data_list, lambda_factor=0.10):
    """
    Applique le modèle EWMA pour estimer la volatilité en utilisant toutes les données disponibles.
    
    :param data_list: Liste des prix historiques (par exemple, mark_price)
    :param lambda_factor: Facteur de lissage pour EWMA
    :return: Volatilité estimée
    """
    global volatility_data  # Utiliser la variable globale pour accumuler les volatilités

    # Extraire les prix de 'mark_price' dans data_list
    prices = pd.Series([item['mark_price'] for item in data_list])

    # Vérifier s'il y a suffisamment de données pour calculer la volatilité
    if len(prices) < 100:
        print("Pas assez de données pour calculer la volatilité.")
        return None

    # Calculer les rendements logarithmiques sur toutes les données disponibles
    returns = np.log(prices / prices.shift(1)).dropna()

    # Vérifier si tous les rendements ne sont pas égaux à 0
    if returns.var() == 0:
        print("Les rendements sont constants, le modèle EWMA ne peut pas être appliqué.")
        return None

    # Initialiser la variance avec la variance empirique
    variance = returns.var()

    # Appliquer le modèle EWMA pour calculer la volatilité
    for r in returns:
        variance = lambda_factor * variance + (1 - lambda_factor) * (r ** 2)

    # La volatilité est la racine carrée de la variance
    volatility = np.sqrt(variance)
    
    print(f"Volatilité estimée (EWMA) : {volatility}")
    
    # Enregistrer la volatilité avec un timestamp
    timestamp = time.time()
    volatility_data.append({'timestamp': timestamp, 'volatility': volatility})

    # Limiter le tableau à 100 dernières valeurs, puis envoyer un e-mail
    if len(volatility_data) >= 100:
        envoyer_email_rapport_volatilites(volatility_data)        
        volatility_data.clear()  
    return volatility



def envoyer_email_rapport_volatilites(volatility_data):
    """
    Envoie un email contenant les 100 derniers indices de volatilité avec leur timestamp.
    """
    # Détails de l'email
    email_expediteur = FROMEMAIL
    mot_de_passe = EMAILPASSWORD
    destinataire_email = TOEMAIL
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






# Fonction appelée lorsqu'un message est reçu
def on_message(ws, message):
    global data_list, collecte_terminee, subscribed_channels, last_volatility_calc_time

    response = json.loads(message)
    print("Message reçu :")
    print(json.dumps(response, indent=4))

    # Si l'authentification est réussie, souscrire aux canaux de prix en temps réel
    if 'result' in response and 'id' in response and response['id'] == 9929:
        print("Authentification réussie, souscription aux canaux...")

        # Souscription au ticker pour recevoir les prix en temps réel
        channel_ticker = "ticker.BTC-PERPETUAL.raw"
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

    # Gestion des messages de données (prix, etc.)
    if 'params' in response and 'data' in response['params']:
        data = response['params']['data']
        timestamp = time.time()  # Récupérer l'horodatage actuel
        
        if 'mark_price' in data:
            print(f"Dernier prix : {data['mark_price']}")

            # Ajouter les données à la liste avec une fenêtre roulante de taille fixe
            data_list.append({
                'timestamp': timestamp,
                'mark_price': data['mark_price']
            })
            progress_percentage = min(100, len(data_list))
            progress_bar.progress(progress_percentage)
            # Maintenir la taille de la fenêtre à 100 éléments
            if len(data_list) > 100:
                data_list.pop(0)  # Retirer l'élément le plus ancien
            
            # Vérifier si 10  secondes se sont écoulées depuis le dernier calcul de volatilité
            if time.time() - last_volatility_calc_time >= 0.1:
                appliquer_modele_ewma(data_list)  # Calculer la volatilité
                update_chart()


                last_volatility_calc_time = time.time()  # Réinitialiser le compteur de temps




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
