#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <pthread.h>
#include <time.h>
#include "core.h"
static u64 Q;
static inline u64 addm(u64 a,u64 b){ u64 s=a+b; if(s>=Q) s-=Q; return s; }
static inline u64 subm(u64 a,u64 b){ return a>=b? a-b : Q-(b-a); }
static void mpow(const u64 base[2], u64 e, u64 out[2]){
    u64 bm[2], rm[2], one[2]={1,0};
    mont_mul(base,R2,bm); mont_mul(R2,one,rm);
    int started=0;
    for(int bit=63;bit>=0;bit--){
        if(started) mont_mul(rm,rm,rm);
        if((e>>bit)&1){ if(!started){rm[0]=bm[0];rm[1]=bm[1];started=1;} else mont_mul(rm,bm,rm); }
    }
    mont_mul(rm,one,rm); memcpy(out,rm,16);
}
static inline u32 hsh(const u64 x[2]){ return (u32)(x[0] ^ (x[0]>>32) ^ x[1] ^ (x[1]>>32)); }
typedef struct { u64 gamma[2],target[2]; u64 seed; int id; volatile int *found; u64 *result; pthread_mutex_t *mtx; } arg_t;
static void *worker(void *vp){
    arg_t *a=(arg_t*)vp;
    u64 gm[2],tm[2];
    mont_mul(a->gamma,R2,gm); mont_mul(a->target,R2,tm);
    srand48(a->seed);
    for(;;){
        if(*a->found) break;
        u64 r1=(((u64)lrand48()<<16)^lrand48())%Q;
        u64 r2=(((u64)lrand48()<<16)^lrand48())%Q;
        u64 p1[2],p2[2],one[2]={1,0};
        mpow(a->gamma,r1,p1); mpow(a->target,r2,p2);
        mont_mul(p1,R2,p1); mont_mul(p2,R2,p2);
        u64 X[2]; mont_mul(p1,p2,X);
        u64 A=r1,B=r2;
        u64 T[2]; memcpy(T,X,16); u64 TA=A,TB=B;
        u64 Hn[2]; memcpy(Hn,X,16); u64 HA=A,HB=B;
        u64 it=0;
        for(;;){
            for(int s=0;s<2;s++){
                u32 k=hsh(Hn)%3;
                if(k==0){ mont_mul(Hn,gm,Hn); HA=addm(HA,1); }
                else if(k==1){ mont_mul(Hn,tm,Hn); HB=addm(HB,1); }
                else { mont_mul(Hn,Hn,Hn); HA=addm(HA,HA); HB=addm(HB,HB); }
            }
            u32 k=hsh(T)%3;
            if(k==0){ mont_mul(T,gm,T); TA=addm(TA,1); }
            else if(k==1){ mont_mul(T,tm,T); TB=addm(TB,1); }
            else { mont_mul(T,T,T); TA=addm(TA,TA); TB=addm(TB,TB); }
            it++;
            if((it&0xFFFFF)==0){ if(*a->found) return 0; }
            if(T[0]==Hn[0]&&T[1]==Hn[1]) break;
        }
        u64 d=subm(TB,HB), e=subm(HA,TA);
        if(d!=0){
            __int128 old_r=d,r=Q,old_s=1,s=0;
            while(r){ __int128 q=old_r/r; __int128 t1=old_r-q*r; old_r=r; r=t1; t1=old_s-q*s; old_s=s; s=t1; }
            if(old_r==1){
                __int128 inv=old_s%(__int128)Q; if(inv<0) inv+=Q;
                u64 x=(u64)(((__int128)e*inv)%(__int128)Q);
                u64 chk[2]; mpow(a->gamma,x,chk);
                if(chk[0]==a->target[0]&&chk[1]==a->target[1]){
                    pthread_mutex_lock(a->mtx);
                    if(!*a->found){ *a->found=1; *a->result=x; }
                    pthread_mutex_unlock(a->mtx);
                    return 0;
                }
            }
        }
    }
    return 0;
}
int main(int argc,char**argv){
    mont_init();
    if(argc<4){ fprintf(stderr,"usage: %s gamma target Q [seed] [nthreads]\n",argv[0]); return 1; }
    u64 gamma[2],target[2]; parse128(argv[1],gamma); parse128(argv[2],target); Q=strtoull(argv[3],0,10);
    u64 seed = argc>4?strtoull(argv[4],0,10):(u64)time(0);
    int nt = argc>5?atoi(argv[5]):2;
    volatile int found=0; u64 result=0; pthread_mutex_t mtx=PTHREAD_MUTEX_INITIALIZER;
    pthread_t th[64]; arg_t args[64];
    for(int i=0;i<nt;i++){ memcpy(args[i].gamma,gamma,16); memcpy(args[i].target,target,16); args[i].seed=seed+i*7919; args[i].id=i; args[i].found=&found; args[i].result=&result; args[i].mtx=&mtx; pthread_create(&th[i],0,worker,&args[i]); }
    // print progress
    for(int i=0;i<nt;i++) pthread_join(th[i],0);
    if(found){ printf("%llu\n",(unsigned long long)result); return 0; }
    return 2;
}
