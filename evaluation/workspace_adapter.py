"""Explicit, lossless-or-rejected mapping of a small AgentDojo workspace subset.

Original benchmark addresses are identities, never SMTP destinations. A trusted
operator must provide an injective identity map into the local test mailbox.
Unsupported fields are rejected rather than silently dropped. No judge is
patched, and no gateway policy is inferred from a benchmark task or tool result.
"""
from dataclasses import dataclass
import re


class IncompatibleSample(ValueError): pass


@dataclass(frozen=True)
class MappedCall:
    id: str
    name: str
    arguments: dict


class WorkspaceMapper:
    def __init__(self,recipients,files):
        if len(set(recipients.values()))!=len(recipients): raise ValueError('Identity mapping must be injective')
        if any(not re.fullmatch(r'[a-z0-9][a-z0-9._+-]*@inbox\.chainguard\.invalid',v) for v in recipients.values()):
            raise ValueError('Only local test mailbox identities are allowed')
        if len(set(files.values()))!=len(files) or any(not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}',v) for v in files.values()):
            raise ValueError('Explicit safe document IDs required')
        self.recipients,self.files=dict(recipients),dict(files)

    def map(self,call):
        name,args=call.function,dict(call.args)
        call_id=call.id
        if not isinstance(call_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',call_id):
            raise IncompatibleSample('EXPLICIT_STABLE_CALL_ID_REQUIRED')
        if name=='send_email':
            if set(args)-{'recipients','subject','body','attachments','cc','bcc'} or not {'recipients','subject','body'}<=set(args):
                raise IncompatibleSample('UNSUPPORTED_MAIL_ARGUMENTS')
            if any(args.get(k) not in (None,[]) for k in ['attachments','cc','bcc']):
                raise IncompatibleSample('ATTACHMENTS_CC_BCC_UNSUPPORTED')
            if not isinstance(args['recipients'],list) or not args['recipients'] or any(r not in self.recipients for r in args['recipients']):
                raise IncompatibleSample('RECIPIENT_IDENTITY_UNMAPPED')
            return MappedCall(call_id,'mail.send',{'to':[self.recipients[r] for r in args['recipients']],
                'subject':args['subject'],'body':args['body']})
        if name in {'get_file_by_id','delete_file'}:
            if set(args)!={'file_id'} or args['file_id'] not in self.files: raise IncompatibleSample('FILE_IDENTITY_UNMAPPED')
            return MappedCall(call_id,'doc.read' if name=='get_file_by_id' else 'doc.delete',{'doc_id':self.files[args['file_id']]})
        raise IncompatibleSample('UNSUPPORTED_WORKSPACE_TOOL:'+name)

    def execute(self,call,proxy):
        # Lazy import keeps the official benchmark environment independent of
        # gateway/chain libraries. A real run always enters the same proxy.
        from chainguard_agent.model import ToolCall
        mapped=self.map(call)
        return proxy.execute(ToolCall(mapped.id,mapped.name,mapped.arguments))
