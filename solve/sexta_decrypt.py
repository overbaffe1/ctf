import struct, hashlib
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

data=open('../sexta.dat','rb').read()
version,modulus=struct.unpack_from('<HH',data,8)
depth=data[13]; n_night=data[14]; n_morning=data[15]; seal=data[16]
n_obs,reference=struct.unpack_from('<HH',data,18)
off=22
night=[list(data[off+i*28:off+(i+1)*28]) for i in range(n_night)]; off+=n_night*28
morning=[list(data[off+i*28:off+(i+1)*28]) for i in range(n_morning)]; off+=n_morning*28
obs=[]
for i in range(n_obs):
    rec=data[off:off+17]; off+=17
    obs.append((list(rec[0:8]),rec[8],list(rec[9:17])))
nonce=data[off:off+12]; off+=12
tag=data[off:off+16]; off+=16
ct_len=struct.unpack_from('<H',data,off)[0]; off+=2
ct=data[off:off+ct_len]
MOD=251
def turn(r,limb):
    a=limb[0:7];b=limb[7:14];c=limb[14:21];d=limb[21:28]
    r=list(r)
    for i in range(7): r[i+1]=(r[i+1]+a[i]*r[i]+b[i])%MOD
    for i in range(6,-1,-1): r[i]=(r[i]+c[i]*r[i+1]+d[i])%MOD
    return r
def code_digits(code,n=7):
    D=[0]*n
    for k in range(n-1,-1,-1):
        D[k]=code&7; code>>=3
    return D
order=1; Fcode=1134862; Gcode=1332613
w=[0,7,2,6,1,4,3,5]
jn=code_digits(Fcode); jm=code_digits(Gcode)
print("decoded jn",jn,"jm",jm)
F,JF=(morning, jn) if order==1 else (night, jn)
G,JG=(night, jm) if order==1 else (morning, jm)
# verify all 16 observations
ok=True
for i,(start,mask,part) in enumerate(obs):
    r=list(start)
    for k in JF: r=turn(r,F[k])
    mid=r[:]
    for k in JG: r=turn(r,G[k])
    fin=r
    for j in range(8):
        if (mask>>j)&1 and fin[w[j]]!=part[j]: ok=False; print("mismatch obs",i,j)
print("all observations verified:", ok)
# seal check
start_ref=obs[reference][0]
r=list(start_ref)
for k in JF: r=turn(r,F[k])
print("seal computed", sum(r)%MOD, "expected", seal)
# trace: state after each turn: first watch then second watch, 2*depth blocks
trace_states=[]
r=list(start_ref)
for k in JF:
    r=turn(r,F[k]); trace_states.append(r[:])
for k in JG:
    r=turn(r,G[k]); trace_states.append(r[:])
print("block depth (handover):", trace_states[depth-1])
print("last block:", trace_states[-1])
# key
keymat = b"SEXTA/handover/3" + b"\x00" + bytes(start_ref) + bytes(trace_states[-1]) \
       + bytes([order]) + bytes(jn) + bytes(jm) + b"".join(bytes(s) for s in trace_states)
key = hashlib.sha256(keymat).digest()
print("key", key.hex())
aad=b"SEXTA/meridian/3"
pt = AESGCM(key).decrypt(nonce, ct+tag, aad)
print("FLAG:", pt)
open('sexta_flag.txt','wb').write(pt)
