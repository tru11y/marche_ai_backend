import os
import json
import requests
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import List
from dotenv import load_dotenv
from groq import Groq
from datetime import datetime
import traceback

# --- IMPORTS PROPRES ---
from .database import engine, get_db, Base
from .models import ProductDB, OrderDB, MessageDB

Base.metadata.create_all(bind=engine)

# --- CONFIGURATION ---
load_dotenv()
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN") # Sera lu depuis Render
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID") # Sera lu depuis Render
GROQ_API_KEY = os.getenv("GROQ_API_KEY") # Sera lu depuis Render
VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "blue_titanium")

client = Groq(api_key=GROQ_API_KEY)

app = FastAPI(title="Marché.AI Enterprise")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# --- OUTILS API ---
class ProductCreate(BaseModel):
    name: str
    price: int
    description: str
    image_url: str = "https://via.placeholder.com/300"

@app.post("/add_product")
def create_product(product: ProductCreate, db: Session = Depends(get_db)):
    db_product = ProductDB(name=product.name, price=product.price, description=product.description, image_url=product.image_url)
    db.add(db_product)
    db.commit()
    return {"status": "success", "message": f"{product.name} ajouté !"}

# --- FONCTIONS WHATSAPP (ENVOI) ---
def send_whatsapp_message(to_number: str, message_text: str):
    url = f"https://graph.facebook.com/v17.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }
    data = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "text",
        "text": {"body": message_text}
    }
    try:
        r = requests.post(url, json=data, headers=headers)
        print(f"📤 Envoi WhatsApp ({r.status_code}): {r.text}")
    except Exception as e:
        print(f"❌ Erreur Envoi: {e}")

# --- LOGIQUE BUSINESS ---
def check_existing_order(phone: str, db: Session):
    return db.query(OrderDB).filter(
        OrderDB.customer_phone == phone, 
        OrderDB.status == "EN_ATTENTE_CAUTION"
    ).order_by(OrderDB.created_at.desc()).first()

def create_order(json_data: dict, phone: str, db: Session):
    if check_existing_order(phone, db): return False 
    try:
        new_order = OrderDB(
            customer_phone=phone,
            product_name=json_data.get("product"),
            customer_name=json_data.get("name"),
            delivery_location=json_data.get("location"),
            amount=json_data.get("price"),
            status="EN_ATTENTE_CAUTION"
        )
        db.add(new_order)
        db.commit()
        return True
    except Exception as e:
        print(f"❌ DB Error: {e}")
        return False

def validate_payment(phone: str, db: Session):
    order = check_existing_order(phone, db)
    if order:
        order.status = "LIVRE_ET_PAYE" 
        db.commit()
        return True
    return False

def generate_dynamic_context(db: Session):
    products = db.query(ProductDB).filter(ProductDB.in_stock == True).all()
    if not products: return "STOCK VIDE."
    txt = "STOCK DISPONIBLE :\n"
    for p in products: txt += f"- {p.name} : {p.price} FCFA [IMAGE: {p.image_url}]\n"
    return txt

def get_chat_history(phone: str, db: Session, limit: int = 6):
    messages = db.query(MessageDB).filter(MessageDB.phone == phone).order_by(MessageDB.id.desc()).limit(limit).all()
    return [{"role": m.role, "content": m.content} for m in reversed(messages)]

def save_message(phone: str, role: str, content: str, db: Session):
    new_msg = MessageDB(phone=phone, role=role, content=content)
    db.add(new_msg)
    db.commit()

def get_ai_response(user_message: str, phone: str, db: Session):
    save_message(phone, "user", user_message, db)
    stock_context = generate_dynamic_context(db)
    chat_history = get_chat_history(phone, db) 
    
    system_prompt = f"""
    TU ES UN VENDEUR EXPERT EN COTE D'IVOIRE.
    {stock_context}
    
    TA STRATÉGIE :
    1. DISCUSSION : Si le client dit bonjour ou pose une question (prix, détails), réponds normalement par du texte (PAS DE JSON).
    2. PHOTO : Si et SEULEMENT SI le client demande explicitement une image ("montre", "photo", "je veux voir") -> JSON "SEND_PHOTO".
    3. COMMANDE : Si le client veut acheter, demande "Nom" et "Quartier".
       Dès que tu as Nom + Quartier -> JSON "FINAL_ORDER".
    4. PAIEMENT : Si le client dit "C'est fait" ou "J'ai payé" -> JSON "CONFIRM_PAYMENT".
    
    FORMATS JSON (Uniquement pour les actions spéciales) :
    {{ "action": "SEND_PHOTO", "product_name": "...", "image_url": "...", "comment": "..." }}
    {{ "action": "FINAL_ORDER", "product": "...", "price": 0, "name": "...", "location": "..." }}
    {{ "action": "CONFIRM_PAYMENT" }}
    """

    try:
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "system", "content": system_prompt}] + chat_history,
            temperature=0.3
        )
        response_content = completion.choices[0].message.content
        
        # Détection du JSON
        if "{" in response_content and "}" in response_content:
            try:
                start = response_content.find('{')
                end = response_content.rfind('}') + 1
                data = json.loads(response_content[start:end])
                
                if data.get("action") == "SEND_PHOTO":
                    reply = f"{data.get('comment')} (Photo: {data.get('image_url')})"
                    save_message(phone, "assistant", reply, db)
                    return reply

                elif data.get("action") == "FINAL_ORDER":
                    if create_order(data, phone, db):
                        reply = "✅ Commande pré-enregistrée ! Pour lancer le livreur, faites le dépôt de 2000F sur le 0707000000. J'attends votre confirmation."
                    else:
                        reply = "J'attends toujours le dépôt de 2000F pour la commande précédente."
                    save_message(phone, "assistant", reply, db)
                    return reply
                
                elif data.get("action") == "CONFIRM_PAYMENT":
                    if validate_payment(phone, db):
                        reply = "🎉 Dépôt confirmé ! Le livreur arrive."
                    else:
                        reply = "Aucune commande en attente de paiement."
                    save_message(phone, "assistant", reply, db)
                    return reply

            except Exception:
                pass
        
        # Si pas de JSON, on renvoie le texte normal
        save_message(phone, "assistant", response_content, db)
        return response_content

    except Exception as e:
        print(f"❌ Erreur IA : {e}")
        return "Petit problème technique..."
    
# --- ROUTES ---

@app.get("/orders")
def get_orders(db: Session = Depends(get_db)):
    # Version simplifiée pour éviter les erreurs de type
    orders = db.query(OrderDB).order_by(OrderDB.created_at.desc()).all()
    return [{"product": o.product_name, "amount": o.amount, "status": o.status, "date": o.created_at} for o in orders]

@app.get("/webhook")
def verify_webhook(request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")
    if mode == "subscribe" and token == VERIFY_TOKEN:
        return int(challenge)
    raise HTTPException(status_code=403, detail="Token invalide")

@app.post("/webhook")
async def receive_message(request: Request, db: Session = Depends(get_db)):
    """La fonction VRAIMENT IMPORTANTE qui reçoit les messages WhatsApp"""
    try:
        data = await request.json()
        
        # On vérifie si c'est un message valide
        if 'entry' in data and 'changes' in data['entry'][0]:
            change = data['entry'][0]['changes'][0]['value']
            
            if 'messages' in change:
                msg_info = change['messages'][0]
                phone = msg_info['from'] # Le numéro du client
                text = msg_info['text']['body'] # Le message écrit
                
                print(f"📩 Reçu de {phone}: {text}")
                
                # 1. On demande à l'IA quoi répondre
                ai_reply = get_ai_response(text, phone, db)
                
                # 2. On envoie la réponse sur WhatsApp
                send_whatsapp_message(phone, ai_reply)
                
                return {"status": "replied"}
                
    except Exception as e:
        print(f"❌ Erreur Webhook : {e}")
        traceback.print_exc()
    
    return {"status": "ok"}