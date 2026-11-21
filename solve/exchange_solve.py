import subprocess, json

p=int.from_bytes(bytes.fromhex("7bf45333234d47dd18d1823272bd2085"),'big')
Q=56175345525792329
M=(p-1)//Q
g=2
h=pow(2,M,p)
fac={4:2,27:3,25:5,7:7,11:11,13:13,17:17,19:19,23:23,29:29,31:31,37:37,41:41,43:43,47:47,53:53}
# checks
prod=1
for qe in fac: prod*=qe
assert prod==M

def ext_gcd(a,b):
    if b==0: return (a,1,0)
    gg,x,y=ext_gcd(b,a%b)
    return (gg,y,x-(a//b)*y)

def crt(res):
    x=0; mod=1
    for m,a in res:
        gg,u,v=ext_gcd(mod,m)
        assert gg==1
        t=((a-x)%m)*u%m
        x+=mod*t; mod*=m; x%=mod
    return x%mod

def dlog_mod_M(A):
    res=[]
    for qe in fac:
        gamma=pow(g,(p-1)//qe,p)
        hq=pow(A,(p-1)//qe,p)
        cur=1; x=None
        for xx in range(qe):
            if cur==hq: x=xx; break
            cur=cur*gamma%p
        assert x is not None
        assert pow(gamma,x,p)==hq
        res.append((qe,x))
    return crt(res)

def dlog_full(A):
    aM=dlog_mod_M(A)
    hQ=pow(A,M,p)
    out=subprocess.run(["./rho",format(h,'x'),format(hQ,'x'),str(Q),"777","2"],capture_output=True,text=True,timeout=900)
    assert out.returncode==0, out.stderr[-400:]
    s=int(out.stdout.strip())
    assert pow(h,s,p)==hQ
    a=crt([(M,aM),(Q,s)])
    assert pow(g,a,p)==A
    return a

cap=json.load(open('../capture.json'))
ops={op['tag']:op for op in cap['operations']}
sess={s['name']:s for s in cap['sessions']}
l=sess[cap['target']]
A=int(ops[l['left_tag']]['result'],16)
B=int(ops[l['right_tag']]['result'],16)
a=dlog_full(A)
print("a =",a)
b=dlog_full(B)
print("b =",b)
K=pow(B,a,p)
assert K==pow(A,b,p)
Kb=K.to_bytes(16,'big')
print("K =",Kb.hex())
ct=bytes.fromhex(cap['ciphertext'])
ks=(Kb*((len(ct)//16)+1))[:len(ct)]
pt=bytes(c^k for c,k in zip(ct,ks))
print("plaintext:", pt)
open('exchange_pt.txt','wb').write(pt)
json.dump({'a':a,'b':b,'K':Kb.hex(),'pt':pt.hex()}, open('dh_result.json','w'), indent=1)
