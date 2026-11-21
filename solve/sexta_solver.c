#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <stdlib.h>
#define MOD 251
#define DEPTH 7
static unsigned char night[8][28], morning[8][28];
static unsigned char obs_start[16][8], obs_mask[16], obs_part[16][8];
static int seal; static unsigned char ref_start[8];
static inline void turn(unsigned char *r, const unsigned char *L){
    for(int i=0;i<7;i++) r[i+1]=(unsigned char)((r[i+1]+L[i]*r[i]+L[7+i])%MOD);
    for(int i=6;i>=0;i--) r[i]=(unsigned char)((r[i]+L[14+i]*r[i+1]+L[21+i])%MOD);
}
static inline uint64_t hash_rows(const unsigned char rows_in[8][9]){
    unsigned char r[8][9]; memcpy(r,rows_in,72);
    for(int i=0;i<8;i++)for(int j=i+1;j<8;j++){
        int cmp=0;
        for(int k=0;k<9;k++){ if(r[i][k]!=r[j][k]){ cmp=(r[i][k]<r[j][k])?-1:1;break;} }
        if(cmp>0) for(int k=0;k<9;k++){unsigned char t=r[i][k];r[i][k]=r[j][k];r[j][k]=t;}
    }
    uint64_t h=1469598103934665603ULL;
    for(int i=0;i<8;i++)for(int k=0;k<9;k++){ h^=r[i][k]; h*=1099511628211ULL; h^=(h>>31); }
    return h;
}
/* growable hash map: key hash -> list of codes, with storing full rows for verification */
typedef struct { uint64_t h; long long code; } ent_t;
typedef struct { ent_t *e; size_t cap, n; } mapl_t;
static void mapl_init(mapl_t*m,size_t cap){ m->e=malloc(cap*sizeof(ent_t)); for(size_t i=0;i<cap;i++) m->e[i].code=-1; m->cap=cap; m->n=0; }
static size_t hn(uint64_t h){ return (size_t)(h ^ (h>>29)); }
static void mapl_add(mapl_t*m, uint64_t h, long long code){
    if((m->n+1)*10 > m->cap*7){
        size_t ncap=m->cap*2; ent_t*ne=malloc(ncap*sizeof(ent_t));
        for(size_t i=0;i<ncap;i++) ne[i].code=-1;
        for(size_t i=0;i<m->cap;i++) if(m->e[i].code>=0){ size_t p=hn(m->e[i].h)%ncap; while(ne[p].code>=0) p=(p+1)%ncap; ne[p]=m->e[i]; }
        free(m->e); m->e=ne; m->cap=ncap;
    }
    size_t p=hn(h)%m->cap; while(m->e[p].code>=0) p=(p+1)%m->cap;
    m->e[p].h=h; m->e[p].code=code; m->n++;
}
static long long *mapl_get(mapl_t*m, uint64_t h, int *cnt){
    long long *res=malloc(64*sizeof(long long)); int n=0,cap=64;
    size_t p=hn(h)%m->cap;
    while(m->e[p].code>=0){
        if(m->e[p].h==h){ if(n==cap){cap*=2;res=realloc(res,cap*sizeof(long long));} res[n++]=m->e[p].code; }
        p=(p+1)%m->cap;
    }
    *cnt=n; return res;
}
static mapl_t gtn, gtm;
static uint64_t g_probe_hash=0; static int g_probe_count=0;
static const unsigned char* g_cur_T=0;
static void build_G(unsigned char (*T)[28], mapl_t *m){
    g_cur_T=(const unsigned char*)T;
    typedef struct { unsigned char st[9][8]; } frame_t;
    static frame_t stack[8]; static int digits[8];
    memset(digits,0,sizeof(digits));
    memset(&stack[0],0,sizeof(frame_t));
    for(int b=0;b<8;b++) stack[0].st[1+b][b]=1;
    int depth=0;
    while(depth>=0){
        if(depth==DEPTH){
            frame_t *fr=&stack[DEPTH];
            long long code=0; for(int k=0;k<DEPTH;k++) code=code*8+digits[k];
            unsigned char rows[8][9];
            for(int i=0;i<8;i++){ for(int k=0;k<8;k++) rows[i][k]=(unsigned char)((fr->st[1+k][i]-fr->st[0][i]+MOD)%MOD); rows[i][8]=fr->st[0][i]; }
            uint64_t hh=hash_rows(rows); if(hh==g_probe_hash) g_probe_count++; if(getenv("SHOWG") && code==atoll(getenv("SHOWG"))) { fprintf(stderr,"G table %s code %lld hash %llu digits:", (g_cur_T==(const unsigned char*)morning)?"morning":"night", code,(unsigned long long)hh); for(int q=0;q<DEPTH;q++) fprintf(stderr," %d",digits[q]); fprintf(stderr,"\n"); } mapl_add(m,hh,code);
            depth--; if(depth>=0) digits[depth]++;
            continue;
        }
        if(digits[depth]<8){
            if(depth+1<8){ memcpy(&stack[depth+1],&stack[depth],sizeof(frame_t)); for(int v=0;v<9;v++) turn(stack[depth+1].st[v],T[digits[depth]]); }
            depth++; if(depth<DEPTH) digits[depth]=0;
        } else { depth--; if(depth>=0) digits[depth]++; }
    }
}
static void code_to_map(unsigned char (*T)[28], long long code, unsigned char M[8][8], int o[8], int idx[DEPTH]){
    long long c=code; for(int k=DEPTH-1;k>=0;k--){ idx[k]=(int)(c&7); c>>=3; }
    unsigned char st[9][8]; memset(st,0,sizeof(st));
    for(int b=0;b<8;b++) st[1+b][b]=1;
    for(int k=0;k<DEPTH;k++) for(int v=0;v<9;v++) turn(st[v],T[idx[k]]);
    for(int i=0;i<8;i++){ o[i]=st[0][i]; for(int b=0;b<8;b++) M[i][b]=(unsigned char)((st[1+b][i]-o[i]+MOD)%MOD); }
}
static int solve_channel(const unsigned char mids[16][8], const int known[], int nknown, const int vals[], unsigned char c[8], int *off){
    int A[16][10];
    for(int i=0;i<nknown;i++){ int t=known[i]; for(int k=0;k<8;k++) A[i][k]=mids[t][k]; A[i][8]=1; A[i][9]=vals[i]; }
    int rr=0,piv[9],npiv=0;
    for(int col=0;col<9 && rr<nknown;col++){
        int p=-1; for(int x=rr;x<nknown;x++) if(A[x][col]%MOD){p=x;break;}
        if(p<0) continue;
        if(p!=rr) for(int k=0;k<10;k++){int t=A[rr][k];A[rr][k]=A[p][k];A[p][k]=t;}
        int inv=1; while((A[rr][col]*inv)%MOD!=1) inv++;
        for(int k=0;k<10;k++) A[rr][k]=(A[rr][k]*inv)%MOD;
        for(int x=0;x<nknown;x++) if(x!=rr && A[x][col]%MOD){ int f=A[x][col]%MOD; for(int k=0;k<10;k++) A[x][k]=(A[x][k]-f*A[rr][k]%MOD+MOD)%MOD; }
        piv[npiv++]=col; rr++;
    }
    for(int x=rr;x<nknown;x++){ int all0=1; for(int k=0;k<9;k++) if(A[x][k]%MOD){all0=0;break;} if(all0&&A[x][9]%MOD) return 0; }
    if(npiv<9) return -1;
    int sol[9]={0};
    for(int i=0;i<npiv;i++) sol[piv[i]]=A[i][9]%MOD;
    for(int k=0;k<8;k++) c[k]=(unsigned char)sol[k];
    *off=sol[8];
    for(int i=0;i<nknown;i++){ int t=known[i]; int v=*off; for(int k=0;k<8;k++) v+=c[k]*mids[t][k]; if(v%MOD!=vals[i]%MOD) return 0; }
    return 1;
}
static FILE *out; static long long nSeal=0,nCand=0;
static void handle_F(int order, unsigned char (*Ftab)[28], unsigned char (*Gtab)[28], mapl_t *Gm, long long Fcode){
    unsigned char Mf[8][8]; int of[8], fidx[DEPTH];
    code_to_map(Ftab,Fcode,Mf,of,fidx);
    unsigned char midref[8];
    for(int i=0;i<8;i++){ int v=of[i]; for(int k=0;k<8;k++) v+=Mf[i][k]*ref_start[k]; midref[i]=(unsigned char)(v%MOD); }
    int s=0; for(int i=0;i<8;i++) s+=midref[i];
    if(s%MOD!=seal) return;
    nSeal++;
    if(getenv("DBG")){ if(Fcode==atoll(getenv("DBG"))) fprintf(stderr,"DBG F matched seal (target)\n"); }
    static int shown=0;
    if(getenv("SHOW") && shown<5){ fprintf(stderr,"sealhit code=%lld\n",Fcode); shown++; }
    unsigned char mids[16][8];
    for(int i=0;i<16;i++){
        for(int r=0;r<8;r++){ int v=of[r]; for(int k=0;k<8;k++) v+=Mf[r][k]*obs_start[i][k]; mids[i][r]=(unsigned char)(v%MOD); }
    }
    unsigned char rows[8][9];
    for(int j=0;j<8;j++){
        int known[16],vals[16],n=0;
        for(int i=0;i<16;i++) if((obs_mask[i]>>j)&1){ known[n]=i; vals[n]=obs_part[i][j]; n++; }
        unsigned char c[8]; int off;
        int r=solve_channel(mids,known,n,vals,c,&off);
        if(r!=1){ if(getenv("DBG") && Fcode==atoll(getenv("DBG"))) fprintf(stderr,"DBG channel %d solve r=%d n=%d\n",j,r,n); return; }
        for(int k=0;k<8;k++) rows[j][k]=c[k];
        rows[j][8]=(unsigned char)off;
    }
    uint64_t h=hash_rows(rows);
    int cnt=0; long long *codes=mapl_get(Gm,h,&cnt);
    if(getenv("DBG") && Fcode==atoll(getenv("DBG"))){
        fprintf(stderr,"DBG Gm lookup cnt=%d hash=%llu\n",cnt,(unsigned long long)h);
        for(int j=0;j<8;j++){ fprintf(stderr,"  solved row %d:",j); for(int k=0;k<9;k++) fprintf(stderr," %d",rows[j][k]); fprintf(stderr,"\n"); }
        unsigned char Mg2[8][8]; int og2[8], gi[DEPTH];
        code_to_map(morning,1801193,Mg2,og2,gi);
        unsigned char rows2[8][9];
        for(int i=0;i<8;i++){ for(int k=0;k<8;k++) rows2[i][k]=Mg2[i][k]; rows2[i][8]=(unsigned char)og2[i]; }
        fprintf(stderr,"DBG true G hash=%llu\n",(unsigned long long)hash_rows(rows2));
        for(int i=0;i<8;i++){ fprintf(stderr,"  true row %d:",i); for(int k=0;k<9;k++) fprintf(stderr," %d",rows2[i][k]); fprintf(stderr,"\n"); }
    }
    for(int ci=0;ci<cnt;ci++){
        long long Gcode=codes[ci];
        unsigned char Mg[8][8]; int og[8], gidx[DEPTH];
        code_to_map(Gtab,Gcode,Mg,og,gidx);
        int w[8], used[8]={0}, good=1;
        for(int j=0;j<8;j++){
            int fl=-1;
            for(int l=0;l<8;l++){
                if(used[l]) continue;
                int same=1;
                for(int k=0;k<8;k++) if(Mg[l][k]!=rows[j][k]){same=0;break;}
                if(same && og[l]==rows[j][8]){ fl=l; break; }
            }
            if(fl<0){ good=0; break; }
            w[j]=fl; used[fl]=1;
        }
        if(!good){ if(getenv("DBG") && Fcode==atoll(getenv("DBG"))) fprintf(stderr,"DBG good=0\n"); continue; }
        int allok=1;
        for(int i=0;i<16 && allok;i++){
            unsigned char fin[8];
            for(int l=0;l<8;l++){ int v=og[l]; for(int k=0;k<8;k++) v+=Mg[l][k]*mids[i][k]; fin[l]=(unsigned char)(v%MOD); }
            for(int j=0;j<8;j++) if((obs_mask[i]>>j)&1) if(fin[w[j]]!=obs_part[i][j]){ allok=0; break; }
        }
        if(!allok){ if(getenv("DBG") && Fcode==atoll(getenv("DBG"))) fprintf(stderr,"DBG allok=0\n"); continue; }
        nCand++;
        fprintf(out,"CAND %d %lld %lld",order,Fcode,Gcode);
        for(int j=0;j<8;j++) fprintf(out," %d",w[j]);
        fprintf(out,"\n");
    }
    free(codes);
}
static unsigned char (*curGtab)[28]; static mapl_t *curGm; static int curOrder;
static void enum_F(unsigned char (*T)[28], int depth, unsigned char st[9][8], long long code){
    if(depth==DEPTH){ handle_F(curOrder,T,curGtab,curGm,code); return; }
    for(int idx=0;idx<8;idx++){
        unsigned char nd[9][8]; memcpy(nd,st,sizeof(nd));
        for(int v=0;v<9;v++) turn(nd[v],T[idx]);
        enum_F(T,depth+1,nd,code*8+idx);
    }
}
int main(int argc,char**argv){
    const char*bf = argc>1? argv[1] : "blob2.bin";
    FILE*f=fopen(bf,"rb");
    fread(night,1,8*28,f); fread(morning,1,8*28,f);
    for(int i=0;i<16;i++){ fread(obs_start[i],1,8,f); fread(&obs_mask[i],1,1,f); fread(obs_part[i],1,8,f); }
    fread(&seal,4,1,f); fread(ref_start,1,8,f); fclose(f);
    { const char*ph=getenv("PROBE"); if(ph) g_probe_hash=strtoull(ph,0,10); }
    fprintf(stderr,"building G tables...\n");
    mapl_init(&gtn, 1<<22); mapl_init(&gtm, 1<<22);
    build_G(night,&gtn); build_G(morning,&gtm);
    fprintf(stderr,"tables built (n=%zu,%zu) probecount=%d\n",gtn.n,gtm.n,g_probe_count);
    out=fopen("cands.txt","w");
    unsigned char st[9][8];
    memset(st,0,sizeof(st)); for(int b=0;b<8;b++) st[1+b][b]=1;
    curOrder=0; curGtab=morning; curGm=&gtm;
    enum_F(night,0,st,0);
    fprintf(stderr,"order0 done: seal %lld cand %lld\n",nSeal,nCand);
    memset(st,0,sizeof(st)); for(int b=0;b<8;b++) st[1+b][b]=1;
    curOrder=1; curGtab=night; curGm=&gtn;
    enum_F(morning,0,st,0);
    fprintf(stderr,"total: seal %lld cand %lld\n",nSeal,nCand);
    fclose(out);
    return 0;
}
