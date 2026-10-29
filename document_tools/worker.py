"""Stateless document worker: stdin/stdout only, no network, mounts or credentials.

The application starts one bounded container per operation. Originals never become paths.
PDF revisions are explicitly reflowed text editions; DOCX revisions keep unaffected content.
"""
import base64
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import zipfile
from xml.etree import ElementTree

MAX_FILE=5*1024*1024
MAX_TEXT=80000

class Rejected(Exception): pass

def require(value,code='DOCUMENT_INVALID'):
    if not value: raise Rejected(code)

def unpack_docx(raw):
    require(raw.startswith(b'PK'))
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        entries=archive.infolist()
        require(len(entries)<=1000 and sum(i.file_size for i in entries)<=25*1024*1024,'DOCUMENT_LIMIT')
        require('[Content_Types].xml' in archive.namelist() and 'word/document.xml' in archive.namelist())
        for entry in entries:
            name=entry.filename.lower()
            require(not name.startswith('/') and '..' not in name.split('/') and '\\' not in name)
            require(not any(x in name for x in ('vbaproject','embeddings/','activex/')),'DOCUMENT_ACTIVE_CONTENT')
            require('_xmlsignatures/' not in name,'DOCUMENT_SIGNATURE_UNSUPPORTED')
            if name.endswith('.rels'):
                root=ElementTree.fromstring(archive.read(entry))
                # Links are not fetched. Reject them as well to keep imported documents inert.
                require(not any(n.attrib.get('TargetMode')=='External' for n in root),'DOCUMENT_EXTERNAL_REFERENCE')
    from docx import Document
    return Document(io.BytesIO(raw))

def paragraphs(document):
    yield from document.paragraphs
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                yield from cell.paragraphs

def convert_doc(raw):
    require(raw.startswith(bytes.fromhex('d0cf11e0a1b11ae1')))
    with tempfile.TemporaryDirectory() as folder:
        source=Path(folder)/'source.doc'; source.write_bytes(raw)
        done=subprocess.run(['/usr/bin/libreoffice','-env:UserInstallation=file://'+folder+'/profile',
            '--headless','--convert-to','docx','--outdir',folder,str(source)],capture_output=True,timeout=35)
        target=Path(folder)/'source.docx'
        require(done.returncode==0 and target.is_file(),'DOCUMENT_CONVERSION_FAILED')
        data=target.read_bytes(); require(len(data)<=MAX_FILE,'DOCUMENT_LIMIT')
        return data

def extract(raw,extension):
    require(0<len(raw)<=MAX_FILE,'DOCUMENT_LIMIT')
    converted=None
    if extension=='doc': converted=convert_doc(raw); extension='docx'; raw=converted
    if extension=='docx':
        doc=unpack_docx(raw)
        units=[{'locator':'paragraph:'+str(i),'text':p.text} for i,p in enumerate(paragraphs(doc),1) if p.text.strip()]
    elif extension=='pdf':
        require(raw.startswith(b'%PDF-'))
        from pypdf import PdfReader
        reader=PdfReader(io.BytesIO(raw),strict=True)
        require(not reader.is_encrypted,'DOCUMENT_ENCRYPTED')
        require(1<=len(reader.pages)<=50,'DOCUMENT_LIMIT')
        require(not reader.trailer['/Root'].get('/AcroForm'),'DOCUMENT_FORMS_UNSUPPORTED')
        units=[{'locator':'page:'+str(i),'text':p.extract_text() or ''} for i,p in enumerate(reader.pages,1)]
        require(any(u['text'].strip() for u in units),'DOCUMENT_OCR_REQUIRED')
    elif extension in {'txt','md'}:
        text=raw.decode('utf-8-sig'); require('\x00' not in text)
        units=[{'locator':'line:'+str(i),'text':line} for i,line in enumerate(text.splitlines(),1) if line.strip()]
    else: raise Rejected('DOCUMENT_FORMAT_UNSUPPORTED')
    require(bool(units),'DOCUMENT_EMPTY')
    require(len(units)<=2000 and sum(len(u['text']) for u in units)<=MAX_TEXT,'DOCUMENT_LIMIT')
    return units,converted

def make_document(title,content,format):
    if format=='docx':
        from docx import Document
        from docx.shared import Pt,RGBColor
        from docx.oxml.ns import qn
        doc=Document(); style=doc.styles['Normal']; style.font.name='WenQuanYi Zen Hei';style.font.size=Pt(11)
        style.element.get_or_add_rPr().get_or_add_rFonts().set(qn('w:eastAsia'),'WenQuanYi Zen Hei')
        title_style=doc.styles['Title'];title_style.font.color.rgb=RGBColor(0,0,0);title_style.font.underline=False
        title_style.font.name='WenQuanYi Zen Hei';title_style.font.size=Pt(22)
        title_style.element.get_or_add_rPr().get_or_add_rFonts().set(qn('w:eastAsia'),'WenQuanYi Zen Hei')
        for border in list(title_style.element.get_or_add_pPr().findall(qn('w:pBdr'))):title_style.element.get_or_add_pPr().remove(border)
        doc.add_paragraph(title,'Title')
        for line in content.splitlines(): doc.add_paragraph(line)
        raw=io.BytesIO(); doc.save(raw); return raw.getvalue()
    require(format=='pdf','DOCUMENT_FORMAT_UNSUPPORTED')
    from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from xml.sax.saxutils import escape
    pdfmetrics.registerFont(TTFont('WQY','/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',subfontIndex=0))
    body=ParagraphStyle('Body',fontName='WQY',fontSize=11,leading=18,wordWrap='CJK',spaceAfter=8)
    heading=ParagraphStyle('Heading',parent=body,fontSize=20,leading=28,spaceAfter=18)
    out=io.BytesIO();doc=SimpleDocTemplate(out,pagesize=(595.28,841.89),leftMargin=54,rightMargin=54,topMargin=54,bottomMargin=54)
    story=[Paragraph(escape(title),heading)]
    for line in content.splitlines(): story.append(Paragraph(escape(line),body) if line else Spacer(1,8))
    doc.build(story);return out.getvalue()

def process(value):
    op=value['op']
    if op=='extract':
        raw=base64.b64decode(value['content_base64'],validate=True)
        units,converted=extract(raw,value['extension'])
        return {'units':units,**({'converted_base64':base64.b64encode(converted).decode()} if converted else {})}
    # Defense in depth: the trusted caller supplies the exact task scope, never the model.
    scope=value['scope']; args=value['arguments']; tool=value['tool']
    require(scope['task_id']==value['task_id'],'UNAUTHORIZED_SCOPE')
    require(scope['expires_at']>time.time(),'DOCUMENT_AUTH_EXPIRED')
    require(tool in scope['tools'],'UNAUTHORIZED_SCOPE')
    source=value.get('source'); source_id=args.get('source_id')
    if source_id:
        require(source_id in scope['attachment_ids'] and source and source['id']==source_id,'UNAUTHORIZED_SCOPE')
        require(hashlib.sha256(base64.b64decode(source['content_base64'],validate=True)).hexdigest()==source['sha256'],'DOCUMENT_INTEGRITY_FAILED')
    if tool=='attachment.read':
        require(source_id,'UNAUTHORIZED_SCOPE')
        units,_=extract(base64.b64decode(source['content_base64'],validate=True),source['extension'])
        start=args['start']; limit=args['limit']
        # Never truncate a unit silently. Response budget is explicit and pageable.
        selected=units[start:start+limit]
        require(sum(len(u['text']) for u in selected)<=24000,'DOCUMENT_READ_LIMIT')
        return {'source_id':source_id,'source_sha256':source['sha256'],'units':selected,'total_units':len(units),'next_start':start+len(selected) if start+len(selected)<len(units) else None}
    require(scope['allow_create'] and tool in {'document.create','document.revise'},'UNAUTHORIZED_SCOPE')
    format=args['format'];title=args['title']; note=None
    if tool=='document.create': raw=make_document(title,args['content'],format)
    else:
        require(source_id and source,'UNAUTHORIZED_SCOPE')
        original=base64.b64decode(source['content_base64'],validate=True)
        units,converted=extract(original,source['extension'])
        old,new=args['find'],args['replace']; count=sum(u['text'].count(old) for u in units)
        require(count>0,'DOCUMENT_TEXT_NOT_FOUND')
        if source['extension'] in {'docx','doc'} and format=='docx':
            doc=unpack_docx(converted or original)
            for p in paragraphs(doc):
                if old in p.text: p.text=p.text.replace(old,new)
            out=io.BytesIO();doc.save(out);raw=out.getvalue()
            note='DOCX_COPY_EDIT; changed paragraphs use plain text runs; original preserved'
        else:
            raw=make_document(title,'\n'.join(u['text'].replace(old,new) for u in units),format)
            note='REFLOWED_TEXT_EDITION; layout, images, forms and signatures are not preserved; original preserved'
    require(len(raw)<=MAX_FILE,'DOCUMENT_LIMIT')
    units,_=extract(raw,format)
    return {'format':format,'content_base64':base64.b64encode(raw).decode(),'sha256':hashlib.sha256(raw).hexdigest(),
        'size':len(raw),'units':units,'note':note,'source_id':source_id,'replacements':count if tool=='document.revise' else 0}

if __name__=='__main__':
    try:
        raw=sys.stdin.buffer.read(8*1024*1024+1); require(len(raw)<=8*1024*1024,'DOCUMENT_LIMIT')
        result=process(json.loads(raw));print(json.dumps({'ok':True,'result':result},ensure_ascii=False))
    except Rejected as error: print(json.dumps({'ok':False,'error':str(error)}))
    except Exception: print(json.dumps({'ok':False,'error':'DOCUMENT_PROCESSING_FAILED'}))
