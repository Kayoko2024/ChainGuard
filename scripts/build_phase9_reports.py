"""Render anonymized Markdown reports into PDFs; no private state or network read."""
import argparse
from html import escape
import json
from pathlib import Path
import re

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from pypdf import PdfReader

ROOT=Path(__file__).resolve().parents[1]


def render(source,output,font):
    text=source.read_text(encoding='utf8')
    # Only these authored reports, never raw manifests, private journals or host logs.
    if re.search(r'(?i)(?:[A-Z]:[\\/]|C:/Users/|sk-[a-z0-9]{12,}|BEGIN .*PRIVATE KEY|github\.com/[^\s]+)',text):
        raise ValueError('Report contains a host path, credential pattern or personal repository URL')
    pdfmetrics.registerFont(TTFont('ReportCJK',str(font)))
    base=dict(fontName='ReportCJK',wordWrap='CJK',alignment=TA_LEFT)
    body=ParagraphStyle('Body',fontSize=9.5,leading=16,spaceAfter=9,**base)
    small=ParagraphStyle('Small',fontSize=8,leading=12,spaceAfter=3,**base)
    heading=ParagraphStyle('Heading',fontSize=14,leading=22,spaceBefore=12,spaceAfter=10,textColor=colors.HexColor('#176a60'),**base)
    title=ParagraphStyle('Title',fontSize=24,leading=34,spaceAfter=16,textColor=colors.HexColor('#143544'),**base)
    story=[]
    lines=text.splitlines();i=0
    while i<len(lines):
        line=lines[i].strip();i+=1
        if not line:continue
        if line=='<!-- pagebreak -->':story.append(PageBreak());continue
        if line.startswith('# '):story.append(Paragraph(escape(line[2:]),title));continue
        if line.startswith('## '):story.append(Paragraph(escape(line[3:]),heading));continue
        if line.startswith('|'):
            rows=[]
            while True:
                if not re.fullmatch(r'[|:\-\s]+',line):
                    rows.append([Paragraph(escape(v.strip()),small) for v in line.strip('|').split('|')])
                if i>=len(lines) or not lines[i].strip().startswith('|'):break
                line=lines[i].strip();i+=1
            table=Table(rows,colWidths=[(A4[0]-100)/len(rows[0])]*len(rows[0]),repeatRows=1,hAlign='LEFT')
            table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e7f2ee')),
                ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f6f8fa')]),
                ('VALIGN',(0,0),(-1,-1),'TOP'),('LINEBELOW',(0,0),(-1,0),.7,colors.HexColor('#91b7ac')),
                ('LEFTPADDING',(0,0),(-1,-1),8),('RIGHTPADDING',(0,0),(-1,-1),8),
                ('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)]))
            story.extend([table,Spacer(1,10)]);continue
        story.append(Paragraph(escape(line),body))
    output.parent.mkdir(parents=True,exist_ok=True)
    doc=SimpleDocTemplate(str(output),pagesize=A4,leftMargin=50,rightMargin=50,topMargin=49,bottomMargin=47,
        title=source.stem+' - ChainGuard',author='',subject='Anonymous competition prototype',creator='ChainGuard report builder')
    def footer(canvas,doc):
        canvas.saveState();canvas.setFont('ReportCJK',8);canvas.setFillColor(colors.HexColor('#6a7f87'))
        canvas.drawString(50,25,'ChainGuard | 匿名竞赛原型 | 协议1.0.0')
        canvas.drawRightString(A4[0]-50,25,str(doc.page));canvas.restoreState()
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    reader=PdfReader(output)
    assert not reader.metadata.get('/Author')
    extracted='\n'.join(p.extract_text() for p in reader.pages)
    assert 'ChainGuard' in extracted and len(extracted)>1000
    return dict(file=output.name,pages=len(reader.pages),author_empty=True,text_extractable=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--font',type=Path,default=Path('C:/Windows/Fonts/simhei.ttf'))
    parser.add_argument('--out',type=Path,default=ROOT/'output/pdf')
    args=parser.parse_args()
    results=[]
    for source,name in [('design-report.md','设计报告+ChainGuard.pdf'),('test-report.md','测试报告+ChainGuard.pdf')]:
        results.append(render(ROOT/'docs/reports'/source,args.out/name,args.font))
    (args.out/'report-validation.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(results,ensure_ascii=False))
