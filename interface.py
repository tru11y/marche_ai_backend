import streamlit as st
import requests

st.set_page_config(page_title="Marché.AI - Test", page_icon="📱")

st.title("📱 Interface WhatsApp (Simulateur)")
st.caption("Test de la logique Mobile Money & Livraison")

# Initialisation
if "messages" not in st.session_state:
    st.session_state.messages = []

# Affichage Historique
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Zone de saisie
if prompt := st.chat_input("Message..."):
    # Afficher User
    with st.chat_message("user"):
        st.markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    # Appel Backend
    try:
        response = requests.post("http://127.0.0.1:8000/chat/test", json={"text": prompt})
        if response.status_code == 200:
            bot_reply = response.json().get("reply")
            with st.chat_message("assistant"):
                st.markdown(bot_reply)
            st.session_state.messages.append({"role": "assistant", "content": bot_reply})
        else:
            st.error("Erreur Backend 404 ou 500")
    except Exception as e:
        st.error(f"Le serveur Python est éteint ! ({e})")