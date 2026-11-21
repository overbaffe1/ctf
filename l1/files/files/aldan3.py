#!/usr/bin/env python3
"""Алдан-3: отладочный эмулятор 45-битной машины. Формат ленты — в паспорте."""
import argparse,json
MASK=(1<<45)-1
def load(path):
    mem=[0]*4096
    for line in open(path,encoding="utf-8-sig"):
        if not line.strip() or line.startswith("*"):continue
        a,v=line.split();mem[int(a,8)]=int(v,8)&MASK
    return mem
def step(m,pc):
    w=m[pc];op=(w>>36)&63;a=(w>>24)&4095;b=(w>>12)&4095;c=w&4095
    nxt=(pc+1)&4095
    if op==0:return None
    if op==1:m[c]=(m[a]+m[b])&MASK
    elif op==2:m[c]=(m[a]-m[b])&MASK
    elif op==4:m[c]=m[a]&m[b]
    elif op==5:m[c]=m[a]|m[b]
    elif op==6:m[c]=m[a]^m[b]
    elif op==7:m[c]=(m[a]<<m[b])&MASK if m[b]<45 else 0
    elif op==8:m[c]=m[a]>>m[b] if m[b]<45 else 0
    elif op==9:m[c]=m[a]
    elif op==10:nxt=c
    elif op==11:
        if m[a]==m[b]:nxt=c
    elif op==12:
        if m[a]!=m[b]:nxt=c
    elif op==13:
        if m[a]<m[b]:nxt=c
    elif op==14:m[c]=m[m[a]&4095]
    elif op==15:print(chr(m[a]&255),end="",flush=True)
    else:raise ValueError(f"Неизвестная команда {op:o} в {pc:04o}")
    return nxt
def main():
    p=argparse.ArgumentParser();p.add_argument("tape");p.add_argument("--limit",type=int,default=1000000)
    p.add_argument("--trace",type=int,default=0);p.add_argument("--pc",type=lambda s:int(s,8),default=0)
    p.add_argument("--patch",action="append",default=[],help="адрес:значение, оба восьмеричные")
    p.add_argument("--dump");a=p.parse_args();m=load(a.tape)
    for item in a.patch:
        k,v=item.split(":");m[int(k,8)]=int(v,8)&MASK
    pc=a.pc
    for i in range(a.limit):
        if i<a.trace:print(f"{pc:04o}: {m[pc]:015o}")
        nxt=step(m,pc)
        if nxt is None:print(f"ОСТ {pc:04o}; {i+1} команд");break
        pc=nxt
    else:print(f"Лимит отладки; следующий адрес {pc:04o}")
    if a.dump:
        with open(a.dump,"w",encoding="utf-8") as f:json.dump({"pc":pc,"memory":m},f)
if __name__=="__main__":main()
