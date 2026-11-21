#ifndef CORE_H
#define CORE_H
#include <stdint.h>
#include <string.h>
typedef unsigned __int128 u128; typedef uint64_t u64; typedef uint32_t u32;
static u64 P[2], NP0, R2[2];
static inline void mont_mul(const u64 a[2], const u64 b[2], u64 r[2]){
    u64 t[4]={0,0,0,0};
    // full product
    for(int i=0;i<2;i++){
        u64 carry=0;
        for(int j=0;j<2;j++){
            u128 uv=(u128)a[j]*b[i]+t[i+j]+carry;
            t[i+j]=(u64)uv; carry=(u64)(uv>>64);
        }
        // propagate carry
        int k=i+2;
        u64 c=carry;
        while(c && k<4){ u64 s=t[k]+c; c=(s<t[k]); t[k]=s; k++; }
    }
    // montgomery reduction
    for(int i=0;i<2;i++){
        u64 m=t[i]*NP0;
        u64 carry=0;
        for(int j=0;j<2;j++){
            u128 uv=(u128)m*P[j]+t[i+j]+carry;
            t[i+j]=(u64)uv; carry=(u64)(uv>>64);
        }
        int k=i+2; u64 c=carry;
        while(c && k<4){ u64 s=t[k]+c; c=(s<t[k]); t[k]=s; k++; }
    }
    u64 lo=t[2], hi=t[3];
    if(hi>P[1] || (hi==P[1] && lo>=P[0])){ u64 br=(lo<P[0]); lo-=P[0]; hi-=P[1]+br; }
    r[0]=lo; r[1]=hi;
}
static inline void mont_init(void){
    P[0]=0x18d1823272bd2085ULL; P[1]=0x7bf45333234d47ddULL;
    u64 inv=1; for(int i=0;i<6;i++) inv=inv*(2-P[0]*inv); NP0=(u64)(0-inv);
    u64 x[2]={1,0};
    for(int i=0;i<256;i++){ u64 y[2]={x[0]<<1,(x[1]<<1)|(x[0]>>63)}; if(y[1]>P[1]||(y[1]==P[1]&&y[0]>=P[0])){u64 br=(y[0]<P[0]);y[0]-=P[0];y[1]-=P[1]+br;} x[0]=y[0];x[1]=y[1]; }
    R2[0]=x[0];R2[1]=x[1];
}
static inline void parse128(const char*s, u64 r[2]){
    u64 hi=0,lo=0;
    for(;*s;s++){ char ch=*s; if(ch=='\n'||ch=='\r'||ch==' ')break;
        u64 d=(ch<='9')?(u64)(ch-'0'):(u64)((ch|32)-'a'+10);
        hi=(hi<<4)|(lo>>60); lo=(lo<<4)|d; }
    r[0]=lo;r[1]=hi;
}
static inline void print128(const u64 r[2]){ printf("%016llx%016llx\n",(unsigned long long)r[1],(unsigned long long)r[0]); }
#endif
