import struct
data=open('../sexta.dat','rb').read()
version,modulus=struct.unpack_from('<HH',data,8)
nregs=data[12]; depth=data[13]; n_night=data[14]; n_morning=data[15]; seal=data[16]; wiring=data[17]
n_obs,reference=struct.unpack_from('<HH',data,18)
off=22
night=[list(data[off+i*28:off+(i+1)*28]) for i in range(n_night)]; off+=n_night*28
morning=[list(data[off+i*28:off+(i+1)*28]) for i in range(n_morning)]; off+=n_morning*28
obs=[]
for i in range(n_obs):
    rec=data[off:off+17]; off+=17
    obs.append((list(rec[0:8]),rec[8],list(rec[9:17])))
MOD=251

def solve_affine(samples, mod=MOD):
    A=[]; b=[]
    for x,y in samples:
        A.append(list(x)+[1]); b.append(y%mod)
    n=len(A); m=9
    M=[row[:]+[b[i]] for i,row in enumerate(A)]
    r=0; piv=[]
    for c in range(m):
        p=None
        for rr in range(r,n):
            if M[rr][c]%mod: p=rr;break
        if p is None: continue
        M[r],M[p]=M[p],M[r]
        inv=pow(M[r][c]%mod,-1,mod)
        M[r]=[(v*inv)%mod for v in M[r]]
        for rr in range(n):
            if rr!=r and M[rr][c]%mod:
                f=M[rr][c]%mod
                M[rr]=[(M[rr][k]-f*M[r][k])%mod for k in range(m+1)]
        piv.append(c); r+=1
    for rr in range(r,n):
        if all(M[rr][k]%mod==0 for k in range(m)) and M[rr][m]%mod!=0:
            return None
    sol=[0]*m
    for i,c in enumerate(piv): sol[c]=M[i][m]%mod
    return sol

Alin=[]; Aoff=[]
for j in range(8):
    S=[(x,partial[j]) for x,mask,partial in obs if (mask>>j)&1]
    sol=solve_affine(S)
    # verify
    for x,y in S:
        assert (sum(x[k]*sol[k] for k in range(8))+sol[8])%MOD==y%MOD
    Alin.append(sol[:8]); Aoff.append(sol[8])
print("A_lin rows:")
for r in Alin: print(r)
print("A_off",Aoff)

blob=bytearray()
for t in night: blob+=bytes(t)
for t in morning: blob+=bytes(t)
for (x,mask,partial) in obs:
    blob+=bytes(x); blob+=bytes([mask]); blob+=bytes(partial)
blob+=struct.pack('<i',seal)
blob+=bytes(obs[reference][0])
for r in Alin: blob+=bytes(r)
blob+=bytes(Aoff)
open('blob2.bin','wb').write(blob)
print("blob2 size",len(blob))
import json
json.dump({'Alin':Alin,'Aoff':Aoff}, open('A.json','w'))
