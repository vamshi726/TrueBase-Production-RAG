import re
import uuid
from pathlib import Path
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from app.observability import initialize
from app.demo_context import principal, Principal
from app.aws import client
from app.config import settings
from app.db import connection, audit
from app.rag import chat
from app.guardrails import check_input, classify_input
from app.memory import history, save_turn, list_messages
from worker.ingest import process_s3_key




initialize()


BASE=Path(__file__).resolve().parent
app=FastAPI(title='Atlas Enterprise RAG',docs_url='/api/docs')
app.mount('/static',StaticFiles(directory=BASE/'static'),name='static')
templates=Jinja2Templates(directory=BASE/'templates')



class Upload(BaseModel):
    filename:str=Field(min_length=1,max_length=180)

class Ask(BaseModel):
    question:str=Field(min_length=3,max_length=2000)
    conversation_id:uuid.UUID|None=None

class Feedback(BaseModel):
    document_id:str|None=None
    rating:int=Field(ge=-1,le=1)
    note:str=Field(default='',max_length=500)



@app.get('/',response_class=HTMLResponse)
def home(request:Request):
    return templates.TemplateResponse('index.html',{'request':request,'region':settings().aws_region,
        'mode':'single-workspace demo'})



@app.get('/health/live')
def live(): return {'status':'alive'}



@app.get('/health/ready')
def ready():
    try:
        with connection() as conn: conn.execute('SELECT 1').fetchone()
        return {'status':'ready'}
    except Exception as exc:
        raise HTTPException(503,'Database unavailable') from exc



@app.post('/api/documents/uploads')
def create_upload(body:Upload,p:Principal=Depends(principal)):
    suffix=Path(body.filename).suffix.lower()
    if suffix not in {'.pdf','.docx','.txt','.md'}:
        raise HTTPException(400,'Allowed types: PDF, DOCX, TXT, MD')
    doc_id=str(uuid.uuid4())
    key=f'tenants/{p.tenant}/incoming/{doc_id}/v1{suffix}'
    with connection() as conn:
        conn.execute('''INSERT INTO documents(id,tenant_id,title,owner_sub,allowed_groups,s3_key,status,current_version)
                        VALUES (%s,%s,%s,%s,%s,%s,'pending',1)''',
                        (doc_id,p.tenant,body.filename,p.subject,["workspace"],key))
        audit(conn,p.subject,p.tenant,'upload_requested',{'document_id':doc_id})
    # Browser PUTs to S3; a separate completion request triggers synchronous ingestion.
    url=client('s3').generate_presigned_url('put_object',Params={'Bucket':settings().s3_bucket,
        'Key':key,'ContentType':'application/octet-stream'},ExpiresIn=300)
    return {'document_id':doc_id,'upload_url':url,'headers':{'Content-Type':'application/octet-stream'}}