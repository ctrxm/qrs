import os
import hmac
import base64
from io import BytesIO
from fastapi import FastAPI, Request, HTTPException, Header
from pydantic import BaseModel
from dotenv import load_dotenv
from qris_payment import QRISPayment

# Muat environment variables dari file .env
load_dotenv()

# --- Konfigurasi Aplikasi ---
class Settings:
    INTERNAL_API_KEY: str = os.getenv("INTERNAL_API_KEY")
    QRIS_CONFIG = {
        'auth_username': os.getenv("QRIS_AUTH_USERNAME"),
        'auth_token': os.getenv("QRIS_AUTH_TOKEN"),
        'base_qr_string': os.getenv("QRIS_BASE_STRING"),
        'logo_path': './logo.png'
    }

settings = Settings()
app = FastAPI(title="MinerX QRIS Service")

# Inisialisasi library QRIS sekali saja saat aplikasi dimulai
qris_processor = QRISPayment(settings.QRIS_CONFIG)

# Tambahan endpoint root supaya akses "/" tidak Not Found
@app.get("/")
async def root():
    return {"message": "MinerX QRIS Service is running"}

# --- Pydantic Models untuk Validasi Data ---
class CreateQrisRequest(BaseModel):
    amount: int
    order_ref: str

class QrisResponse(BaseModel):
    order_ref: str
    amount: int
    qr_image_base64: str

class CheckStatusRequest(BaseModel):
    order_ref: str
    amount: int

class StatusResponse(BaseModel):
    status: str  # "PENDING" atau "PAID"

# --- Middleware Keamanan untuk API Internal ---
@app.middleware("http")
async def secure_internal_api(request: Request, call_next):
    # Hanya endpoint yang perlu diamankan yang diperiksa
    if request.url.path in ["/create-qris", "/check-payment"]:
        api_key = request.headers.get("X-API-KEY")
        if not api_key or not hmac.compare_digest(api_key, settings.INTERNAL_API_KEY):
            raise HTTPException(status_code=403, detail="Forbidden: Invalid API Key")
    response = await call_next(request)
    return response

# --- Endpoints API ---
@app.post("/create-qris", response_model=QrisResponse)
async def create_qris(payload: CreateQrisRequest):
    """Endpoint untuk membuat QR code dinamis, dipanggil oleh server PHP."""
    try:
        result = qris_processor.generate_qr(payload.amount)
        qr_image = result.get('qr_image')
        if not qr_image:
            raise HTTPException(status_code=500, detail="Library QRIS gagal membuat gambar.")
        
        # Konversi gambar ke format base64 untuk dikirim via JSON
        buffered = BytesIO()
        qr_image.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode('utf-8')

        return QrisResponse(
            order_ref=payload.order_ref,
            amount=payload.amount,
            qr_image_base64=f"data:image/png;base64,{img_str}"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error saat generate QR: {e}")

@app.post("/check-payment", response_model=StatusResponse)
async def check_payment_status(payload: CheckStatusRequest):
    """Endpoint untuk memeriksa status pembayaran, dipanggil berulang kali oleh PHP."""
    try:
        payment_result = qris_processor.check_payment(payload.order_ref, payload.amount)
        
        # Sesuaikan logika ini dengan respons asli dari library `qris-payment` Anda
        if payment_result.get('success') and payment_result.get('data', {}).get('status') == 'PAID':
            status = "PAID"
        else:
            status = "PENDING"
            
        return StatusResponse(status=status)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error saat memeriksa pembayaran: {e}")
