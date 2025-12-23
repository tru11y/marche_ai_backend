import requests

# 🚨 REMETS TES CLÉS ACTUELLES ICI
WHATSAPP_TOKEN = "EAAQqrtxFDvgBQb3ohFULL1nEqvnjKmJMrmvD1EYG1sxjodPnPwgTfWTRIj9VZBQNQe6Kau8qwoeYxvZCTa2ceQP4RLPmMc7ZBbZBTcKkq0EyYZAyRwg4bUtw81e2Atk9ZAleZBXSv0pgpTO8nrCm2v47KFA28LPClxhxHdGPDhXLo6IzlS3N9lWcjuwN9BQyrGVM5ZAHnMWSYYrvykU3eJHAvEGaW58IZCCjvB6oXBfgumvZBU2ZChOAN7e9H3nEgsKthsw4HWq6Y8E07Awpv3lKEjUfPTn5JC8PagiRzLHrl0ZD"
PHONE_NUMBER_ID = "917404068122832"

# TON NUMÉRO (Celui qui envoie les messages dans les logs précédents)
# J'ai repris celui de tes logs : 2250705440974
TO_NUMBER = "2250705440974" 

def send_text():
    print("Tentative envoi TEXTE...")
    url = f"https://graph.facebook.com/v17.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    data = {
        "messaging_product": "whatsapp",
        "to": TO_NUMBER,
        "type": "text",
        "text": {"body": "🔔 TEST TECHNIQUE : Est-ce que tu reçois ça ?"}
    }
    r = requests.post(url, json=data, headers=headers)
    print(f"Code Retour: {r.status_code}")
    print(f"Réponse Facebook: {r.text}")

def send_image():
    print("\nTentative envoi IMAGE (Test URL simple)...")
    # On utilise une image très légère et sûre (Wikipédia) au lieu de Apple
    safe_image_url = "https://upload.wikimedia.org/wikipedia/commons/thumb/b/b6/Image_created_with_a_mobile_phone.png/640px-Image_created_with_a_mobile_phone.png"
    
    url = f"https://graph.facebook.com/v17.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    data = {
        "messaging_product": "whatsapp",
        "to": TO_NUMBER,
        "type": "image",
        "image": {"link": safe_image_url, "caption": "Test Image Sûre"}
    }
    r = requests.post(url, json=data, headers=headers)
    print(f"Code Retour: {r.status_code}")
    print(f"Réponse Facebook: {r.text}")

# --- ROUTE SPÉCIALE POUR LE TESTEUR STREAMLIT ---
class TestMessage(BaseModel):
    text: str
    phone: str = "22500000000" # Numéro fictif pour le test

@app.post("/chat/test")
def test_chat(msg: TestMessage, db: Session = Depends(get_db)):
    """Permet de discuter avec l'IA sans passer par WhatsApp"""
    print(f"🧪 Test User: {msg.text}")
    
    # On appelle le cerveau directement
    response = get_ai_response(msg.text, msg.phone, db)
    
    return {"reply": response}

if __name__ == "__main__":
    send_text()
    send_image()