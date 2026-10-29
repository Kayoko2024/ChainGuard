"""Bounded UTF-8 tabular preview. No file paths, execution, persistence or network."""
import csv
import io
import re
from .canonical import canonical,parse_json
from .custom_tools import FIELD
from chainguard_sandbox.protocol import ToolError

def preview(value):
    if type(value) is not dict or set(value)!={'format','content','column_types'}:raise ToolError('SCHEMA_INVALID')
    kind,content,types=value['format'],value['content'],value['column_types']
    if type(kind) is not str or kind not in {'csv','json'} or type(content) is not str or type(types) is not dict:raise ToolError('SCHEMA_INVALID')
    try:
        if not 0<len(content.encode('utf8'))<=65536 or '\x00' in content:raise ToolError('SCHEMA_INVALID')
    except UnicodeEncodeError:raise ToolError('SCHEMA_INVALID') from None
    content=content.removeprefix('\ufeff')
    if kind=='json':
        if types:raise ToolError('SCHEMA_INVALID')
        rows=parse_json(content.encode('utf8'))
    else:
        try:
            source=csv.reader(io.StringIO(content,newline=''),strict=True)
            columns=[c.strip() for c in next(source)]
            if not columns or len(columns)!=len(set(columns)) or any(not FIELD.fullmatch(c) for c in columns):raise ToolError('SCHEMA_INVALID')
            if not set(types)<=set(columns) or any(type(t) is not str or t not in {'string','integer','boolean'} for t in types.values()):raise ToolError('SCHEMA_INVALID')
            rows=[]
            for cells in source:
                if not cells:continue
                if len(cells)!=len(columns) or len(rows)>=200:raise ToolError('SCHEMA_INVALID')
                row={}
                for column,cell in zip(columns,cells):
                    t=types.get(column,'string')
                    if t=='integer':
                        if not re.fullmatch(r'-?(0|[1-9][0-9]*)',cell.strip()):raise ToolError('SCHEMA_INVALID')
                        row[column]=int(cell.strip())
                    elif t=='boolean':
                        if cell.strip() not in {'true','false'}:raise ToolError('SCHEMA_INVALID')
                        row[column]=cell.strip()=='true'
                    else:row[column]=cell
                rows.append(row)
        except (csv.Error,StopIteration,ValueError):raise ToolError('SCHEMA_INVALID') from None
    if type(rows) is not list or not 1<=len(rows)<=200 or any(type(r) is not dict for r in rows):raise ToolError('SCHEMA_INVALID')
    columns=list(rows[0]);observed={}
    if not 1<=len(columns)<=12 or any(not FIELD.fullmatch(c) for c in columns):raise ToolError('SCHEMA_INVALID')
    for row in rows:
        if set(row)!=set(columns):raise ToolError('SCHEMA_INVALID')
        for column,cell in row.items():
            t={str:'string',int:'integer',bool:'boolean'}.get(type(cell))
            if t is None or column in observed and observed[column]!=t:raise ToolError('SCHEMA_INVALID')
            if t=='string' and len(cell)>500 or t=='integer' and abs(cell)>2**53-1:raise ToolError('SCHEMA_INVALID')
            observed[column]=t
    if len(canonical(rows))>32768:raise ToolError('SCHEMA_INVALID')
    return {'records':rows,'columns':columns,'column_types':observed,'row_count':len(rows),'persisted':False}
