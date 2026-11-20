import sys
b=open(sys.argv[1],"rb").read()
def varint(b,i):
    v=s=0
    while True:
        c=b[i]; i+=1; v|=(c&0x7f)<<s; s+=7
        if c<0x80: return v,i
def fields(b):
    i=0
    while i<len(b):
        k,i=varint(b,i); f,wt=k>>3,k&7
        if wt==0: v,i=varint(b,i); yield f,v
        elif wt==2: l,i=varint(b,i); yield f,b[i:i+l]; i+=l
        elif wt==1: i+=8
        elif wt==5: i+=4
print(sum(1 for f,d in fields(b) if f==2 for g,_ in fields(d) if g==4))
