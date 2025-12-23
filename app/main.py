import os
import json
import requests
from fastapi import FastAPI, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import List
from dotenv import load_dotenv
from groq import Groq
from datetime import datetime  # <--- C'ÉTAIT L'IMPORT MANQUANT !

# --- IMPORTS PROPRES (Architecture Modulaire) ---
from .database import engine, get_db, Base
from .models import ProductDB, OrderDB, MessageDB

# Création automatique des tables dans PostgreSQL au démarrage
Base.metadata.create_all(bind=engine)

# --- CONFIGURATION ---
load_dotenv()
# Récupération des clés depuis le .env ou Docker
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "TOKEN_PAR_DEFAUT")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID", "ID_PAR_DEFAUT")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "METS_TA_CLE_GROQ_ICI_OU_DANS_ENV")

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

# --- LOGIQUE BUSINESS (LE CERVEAU) ---

def check_existing_order(phone: str, db: Session):
    return db.query(OrderDB).filter(
        OrderDB.customer_phone == phone, 
        OrderDB.status == "EN_ATTENTE_CAUTION"
    ).order_by(OrderDB.created_at.desc()).first()

def create_order(json_data: dict, phone: str, db: Session):
    if check_existing_order(phone, db):
        return False 
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
        print(f"💰 COMMANDE EN ATTENTE : {json_data.get('product')}")
        return True
    except Exception as e:
        print(f"❌ Erreur DB commande : {e}")
        return False

def validate_payment(phone: str, db: Session):
    order = check_existing_order(phone, db)
    if order:
        order.status = "LIVRE_ET_PAYE" 
        db.commit()
        print(f"✅ PAIEMENT REÇU pour {order.customer_name}. Statut mis à jour.")
        return True
    return False

def generate_dynamic_context(db: Session):
    products = db.query(ProductDB).filter(ProductDB.in_stock == True).all()
    if not products: return "STOCK VIDE. Dis au client qu'on attend le réassort."
    txt = "STOCK DISPONIBLE :\n"
    for p in products: 
        txt += f"- {p.name} : {p.price} FCFA [IMAGE: {p.image_url}]\n"
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
    
    TA STRATÉGIE EN 3 ÉTAPES :
    
    ÉTAPE 1 : CONVAINCRE
    Si le client veut voir : JSON "SEND_PHOTO".
    Si le client veut acheter : Demande "Nom" et "Quartier".
    
    ÉTAPE 2 : PRENDRE LA COMMANDE
    Si tu as Nom + Quartier, utilise le JSON "FINAL_ORDER".
    -> Dans ton texte, dis : "Commande notée. Pour valider l'expédition, faites le dépôt de 2000F sur le 0707000000".
    
    ÉTAPE 3 : VALIDER LE PAIEMENT (IMPORTANT)
    Si le client dit "C'est fait", "J'ai payé", "Capture envoyée" ET que tu as déjà demandé le paiement avant :
    -> UTILISE LE JSON "CONFIRM_PAYMENT".
    -> Ne repose pas de question. Dis juste "Bien reçu, le livreur arrive."
    
    FORMATS JSON :
    {{ "action": "SEND_PHOTO", "product_name": "...", "image_url": "...", "comment": "..." }}
    {{ "action": "FINAL_ORDER", "product": "...", "price": 0, "name": "...", "location": "..." }}
    {{ "action": "CONFIRM_PAYMENT" }}
    """

    messages_payload = [{"role": "system", "content": system_prompt}]
    messages_payload.extend(chat_history)

    try:
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages_payload,
            temperature=0.3
        )
        response_content = completion.choices[0].message.content
        
        if "{" in response_content and "}" in response_content:
            try:
                start = response_content.find('{')
                end = response_content.rfind('}') + 1
                json_str = response_content[start:end]
                data = json.loads(json_str)
                
                if data.get("action") == "SEND_PHOTO":
                    reply = f"[BOT ENVOIE PHOTO] {data.get('comment')} (Lien: {data.get('image_url')})"
                    save_message(phone, "assistant", reply, db)
                    return reply

                elif data.get("action") == "FINAL_ORDER":
                    if create_order(data, phone, db):
                        reply = "✅ Commande pré-enregistrée ! Pour que le livreur démarre, veuillez faire le dépôt de 2000F sur le 0707000000 (Wave/OM). J'attends votre confirmation."
                    else:
                        reply = "Votre commande est déjà en attente du dépôt de 2000F. Dès que c'est fait, dites-le moi !"
                    save_message(phone, "assistant", reply, db)
                    return reply
                
                elif data.get("action") == "CONFIRM_PAYMENT":
                    if validate_payment(phone, db):
                        reply = "🎉 Dépôt confirmé ! Votre commande passe en priorité. Le livreur Yango va vous appeler."
                    else:
                        reply = "Je ne trouve pas de commande en attente pour vous. Voulez-vous commander ?"
                    save_message(phone, "assistant", reply, db)
                    return reply

            except Exception:
                pass
        
        save_message(phone, "assistant", response_content, db)
        return response_content

    except Exception as e:
        print(f"❌ Erreur IA : {e}")
        return "Petit problème technique..."

# --- API ---
class OrderResponse(BaseModel):
    id: int
    product_name: str
    amount: int
    status: str
    created_at: datetime
    class Config: from_attributes = True

@app.get("/orders", response_model=List[OrderResponse])
def get_orders(db: Session = Depends(get_db)):
    return db.query(OrderDB).order_by(OrderDB.created_at.desc()).all()

class TestMessage(BaseModel):
    text: str
    phone: str = "225_TESTEUR"

@app.post("/chat/test")
def test_chat(msg: TestMessage, db: Session = Depends(get_db)):
    response = get_ai_response(msg.text, msg.phone, db)
    return {"reply": response}

@app.post("/webhook")
async def receive_message(request: Request):
    return {"status": "ok"}