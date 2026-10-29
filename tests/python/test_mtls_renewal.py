"""Real OpenSSL renewal must retain identities, keys and strict TLS validation."""
import hashlib
import importlib.util
from pathlib import Path
import shutil
import ssl
import subprocess

import pytest

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('renew_mtls',ROOT/'scripts/renew_phase10_mtls.py')
renew=importlib.util.module_from_spec(spec);spec.loader.exec_module(renew)


@pytest.fixture(scope='module')
def bundle(tmp_path_factory):
    if not shutil.which('openssl'):pytest.skip('Native OpenSSL required for real certificate tests')
    root=tmp_path_factory.mktemp('tls');old=root/'original';old.mkdir()
    openssl=renew.OpenSSL()
    openssl('req','-x509','-newkey','rsa:2048','-nodes','-keyout',old/'ca.key','-out',old/'ca.pem',
            '-subj','/CN=local-test-ca','-days','2','-addext','basicConstraints=critical,CA:TRUE',
            '-addext','keyUsage=critical,keyCertSign,cRLSign')
    for name in renew.NAMES[1:]:
        usage='serverAuth' if name.endswith('server') else 'clientAuth'
        ext=old/(name+'.ext')
        ext.write_text('basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\nextendedKeyUsage='+usage+
                       ('\nsubjectAltName=DNS:phase6-gateway' if name=='gateway-server' else '')+'\n')
        openssl('req','-new','-newkey','rsa:2048','-nodes','-keyout',old/(name+'.key'),'-out',old/(name+'.csr'),'-subj','/CN='+name)
        openssl('x509','-req','-in',old/(name+'.csr'),'-CA',old/'ca.pem','-CAkey',old/'ca.key','-set_serial',str(renew.NAMES.index(name)),
                '-days','2','-extfile',ext,'-out',old/(name+'.pem'))
    original={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in old.iterdir()}
    new=root/'new';certs=renew.renew_bundle(old,new,openssl)
    return old,new,certs,original


def test_renewal_keeps_originals_and_keys_with_exact_seven_day_leaf_validity(bundle):
    old,new,certs,original=bundle
    assert {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in old.iterdir()}==original
    assert not list(new.glob('*.key'))
    for name in renew.NAMES:
        before,after=renew.metadata(old/(name+'.pem')),renew.metadata(new/(name+'.pem'))
        assert before['subject']==after['subject'] and before['subjectAltName']==after['subjectAltName']
        validity=ssl.cert_time_to_seconds(after['notAfter'])-ssl.cert_time_to_seconds(after['notBefore'])
        assert validity==(365 if name=='ca' else 7)*86400
        assert certs[name]==(new/(name+'.pem')).read_bytes()


def test_certificates_keep_their_server_client_usage_and_hostname_guards(bundle):
    _,new,_,_=bundle;openssl=renew.OpenSSL()
    openssl('verify','-CAfile',new/'ca.pem','-purpose','sslserver','-verify_hostname','phase6-gateway',new/'gateway-server.pem')
    with pytest.raises(RuntimeError):
        openssl('verify','-CAfile',new/'ca.pem','-purpose','sslserver','-verify_hostname','attacker.invalid',new/'gateway-server.pem')
    with pytest.raises(RuntimeError):
        openssl('verify','-CAfile',new/'ca.pem','-purpose','sslserver',new/'agent.pem')


def test_expired_certificate_is_still_rejected_after_ca_renewal(bundle):
    old,new,_,_=bundle;openssl=renew.OpenSSL();expired=new/'expired.pem'
    openssl('x509','-req','-in',old/'gateway-server.csr','-CA',new/'ca.pem','-CAkey',old/'ca.key','-set_serial','999',
            '-days','-1','-extfile',old/'gateway-server.ext','-out',expired)
    with pytest.raises(RuntimeError):openssl('verify','-CAfile',new/'ca.pem',expired)


def test_pin_updates_change_no_other_configuration_and_detect_stale_pins(bundle):
    _,_,certs,_=bundle
    previous={'operator_fingerprint':'old','authority_fingerprint':'previous-tool','roles':['original'],'token':'local-test-secret'}
    expected={k:previous[k] for k in ['operator_fingerprint','authority_fingerprint']}
    replacement=renew.pins('gateway',certs)
    result=renew.renewed_runtime(previous,expected,replacement)
    assert result=={**previous,**replacement} and previous['operator_fingerprint']=='old'
    assert result['operator_fingerprint']!=renew.fingerprint(certs['agent'])
    with pytest.raises(ValueError):renew.renewed_runtime(previous,{'operator_fingerprint':'unexpected'}, {'operator_fingerprint':'new'})
    with pytest.raises(ValueError):renew.renewed_runtime(previous,{'token':'local-test-secret'}, {'token':'replacement'})


@pytest.mark.parametrize('days,ca_days',[(2,365),(7,7),(366,3650),(7,4000)])
def test_invalid_validity_cannot_create_staging_directory(tmp_path,days,ca_days):
    with pytest.raises(ValueError):renew.renew_bundle(tmp_path,tmp_path/'new',None,days,ca_days)
    assert not (tmp_path/'new').exists()
