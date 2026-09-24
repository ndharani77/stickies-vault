from datetime import datetime, timedelta, timezone
from typing import List
import os
import json
import re

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, create_engine, text
from sqlalchemy.orm import Session, declarative_base, relationship, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./secure_notes.db")
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, index=True, nullable=False)
    email = Column(String(254), unique=True, index=True, nullable=True)
    password_hash = Column(String(255), nullable=False)
    notes = relationship("Note", back_populates="owner", cascade="all, delete-orphan")
    folders = relationship("Folder", back_populates="owner", cascade="all, delete-orphan")

class Note(Base):
    __tablename__ = "notes"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    owner = relationship("User", back_populates="notes")

class Folder(Base):
    __tablename__ = "folders"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_user_folder_name"),)
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    owner = relationship("User", back_populates="folders")

Base.metadata.create_all(bind=engine)
with engine.begin() as connection:
    columns = {row[1] for row in connection.execute(text("PRAGMA table_info(users)"))}
    if "email" not in columns:
        connection.execute(text("ALTER TABLE users ADD COLUMN email VARCHAR(254)"))

app = FastAPI(title="Secure Notes API", description="Backend API for Stickies Vault", version="3.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"])

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
SECRET_KEY = os.getenv("SECRET_KEY", "CHANGE_THIS_SECRET_KEY_BEFORE_PRODUCTION")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
security = HTTPBearer(auto_error=False)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)

def create_access_token(user_id: int, username: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": str(user_id), "username": username, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)):
    if credentials is None:
        raise HTTPException(status_code=401, detail="Missing bearer token")
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        user = db.query(User).filter(User.id == int(user_id)).first()
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        return user
    except (JWTError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid or expired token")

class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=100)
    email: str | None = Field(default=None, min_length=5, max_length=254)
    password: str = Field(min_length=4, max_length=100)
class PasswordRecovery(BaseModel):
    username: str = Field(min_length=3, max_length=100)
    email: str = Field(min_length=5, max_length=254)
    new_password: str = Field(min_length=4, max_length=100)
class LoginRequest(BaseModel):
    username: str
    password: str
class PasswordChange(BaseModel):
    current_password: str = Field(min_length=4, max_length=100)
    new_password: str = Field(min_length=4, max_length=100)
class NoteCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str
class NoteUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str
class NoteResponse(BaseModel):
    id: int
    title: str
    content: str
    created_at: datetime
    updated_at: datetime
    class Config:
        from_attributes = True
class FolderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
class FolderUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
class FolderResponse(BaseModel):
    id: int
    name: str
    created_at: datetime
    class Config:
        from_attributes = True

@app.get("/")
def root():
    return {"success": True, "message": "Secure Notes API is running"}

@app.get("/health")
def health():
    return {"success": True, "status": "healthy"}

@app.post("/register")
def register_user(user: UserCreate, db: Session = Depends(get_db)):
    email = user.email.strip().lower() if user.email else None
    if email and not re.fullmatch(r"[^\s@]+@gmail\.com", email):
        raise HTTPException(status_code=422, detail="Use a valid Gmail address")
    existing_user = db.query(User).filter(User.username == user.username).first()
    if existing_user:
        raise HTTPException(status_code=409, detail="Username already exists")
    existing_email = db.query(User).filter(User.email == email).first() if email else None
    if existing_email:
        raise HTTPException(status_code=409, detail="Gmail address already exists")
    new_user = User(username=user.username, email=email, password_hash=hash_password(user.password))
    db.add(new_user); db.commit(); db.refresh(new_user)
    return {"success": True, "message": "User registered successfully", "user": {"id": new_user.id, "username": new_user.username, "email": new_user.email}}

@app.post("/forgot-password")
def recover_password(payload: PasswordRecovery, db: Session = Depends(get_db)):
    email = payload.email.strip().lower()
    user = db.query(User).filter(User.username == payload.username.strip(), User.email == email).first()
    if not user:
        raise HTTPException(status_code=400, detail="Username and Gmail address do not match")
    user.password_hash = hash_password(payload.new_password)
    db.commit()
    return {"success": True, "message": "PIN reset successfully"}

@app.post("/login")
def login_user(login: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == login.username).first()
    if not user or not verify_password(login.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = create_access_token(user.id, user.username)
    return {"success": True, "message": "Login successful", "access_token": token, "token_type": "bearer", "user": {"id": user.id, "username": user.username}}

@app.get("/me")
def get_me(current_user: User = Depends(get_current_user)):
    return {"success": True, "user": {"id": current_user.id, "username": current_user.username}}

@app.put("/me/password")
def change_password(payload: PasswordChange, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Current PIN is incorrect")
    if payload.current_password == payload.new_password:
        raise HTTPException(status_code=400, detail="New PIN must be different")
    current_user.password_hash = hash_password(payload.new_password)
    db.commit()
    return {"success": True, "message": "Master PIN changed successfully"}

@app.post("/notes", response_model=NoteResponse)
def create_note(note: NoteCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    new_note = Note(title=note.title, content=note.content, user_id=current_user.id)
    db.add(new_note); db.commit(); db.refresh(new_note)
    return new_note

@app.get("/notes", response_model=List[NoteResponse])
def get_notes(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(Note).filter(Note.user_id == current_user.id).order_by(Note.updated_at.desc()).all()

@app.get("/notes/{note_id}", response_model=NoteResponse)
def get_note(note_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    note = db.query(Note).filter(Note.id == note_id, Note.user_id == current_user.id).first()
    if not note: raise HTTPException(status_code=404, detail="Note not found")
    return note

@app.put("/notes/{note_id}", response_model=NoteResponse)
def update_note(note_id: int, note_data: NoteUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    note = db.query(Note).filter(Note.id == note_id, Note.user_id == current_user.id).first()
    if not note: raise HTTPException(status_code=404, detail="Note not found")
    note.title = note_data.title; note.content = note_data.content; note.updated_at = datetime.utcnow()
    db.commit(); db.refresh(note)
    return note

@app.delete("/notes/{note_id}")
def delete_note(note_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    note = db.query(Note).filter(Note.id == note_id, Note.user_id == current_user.id).first()
    if not note: raise HTTPException(status_code=404, detail="Note not found")
    db.delete(note); db.commit()
    return {"success": True, "message": "Note deleted successfully"}

@app.get("/folders", response_model=List[FolderResponse])
def get_folders(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(Folder).filter(Folder.user_id == current_user.id).order_by(Folder.name.asc()).all()

@app.post("/folders", response_model=FolderResponse)
def create_folder(folder: FolderCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    name = folder.name.strip()
    existing = db.query(Folder).filter(Folder.user_id == current_user.id, Folder.name == name).first()
    if existing:
        raise HTTPException(status_code=409, detail="Folder already exists")
    new_folder = Folder(name=name, user_id=current_user.id)
    db.add(new_folder); db.commit(); db.refresh(new_folder)
    return new_folder

@app.put("/folders/{folder_id}", response_model=FolderResponse)
def rename_folder(folder_id: int, folder: FolderUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    target = db.query(Folder).filter(Folder.id == folder_id, Folder.user_id == current_user.id).first()
    if not target: raise HTTPException(status_code=404, detail="Folder not found")
    name = folder.name.strip()
    duplicate = db.query(Folder).filter(Folder.user_id == current_user.id, Folder.name == name, Folder.id != folder_id).first()
    if duplicate: raise HTTPException(status_code=409, detail="Folder already exists")
    target.name = name
    db.commit(); db.refresh(target)
    return target

@app.delete("/folders/{folder_id}")
def delete_folder(folder_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    target = db.query(Folder).filter(Folder.id == folder_id, Folder.user_id == current_user.id).first()
    if not target:
        raise HTTPException(status_code=404, detail="Folder not found")
    notes = db.query(Note).filter(Note.user_id == current_user.id).all()
    for note in notes:
        try:
            meta = json.loads(note.content or "{}")
        except Exception:
            continue
        if meta.get("folderId") == folder_id:
            meta["folderId"] = None
            note.content = json.dumps(meta)
            note.updated_at = datetime.utcnow()
    db.delete(target)
    db.commit()
    return {"success": True, "message": "Folder deleted. Notes were moved to Unfiled."}
