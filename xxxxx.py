import pandas as pd
import numpy as np

ma5=pd.Series(np.random.randn(10))
ma10=pd.Series(np.random.randn(10))
df=pd.DataFrame({'A':ma5,'B':ma10})
index1=df.loc[df['A']>df['B']].index
index2=df.loc[df['A']<df['B']].index
index3=df.loc[df['A']==df['B']].index
biger=pd.Series(1,index=index1)
smaller=pd.Series(-1,index=index2)
equare=pd.Series(2,index=index3)
df['Bigger']=biger
df['Smaller']=smaller
df=df.fillna(0)
df['trend']=df['Bigger']+df['Smaller']
df['trend1']=df['trend'].shift(1).fillna(0)
upindex=df.loc[df['trend']>df['trend1']].index
downindex=df.loc[df['trend']<df['trend1']].index
uptrend=pd.Series(1,index=upindex)
downtrend=pd.Series(-1,index=downindex)
df['uptrend']=uptrend
df['downtrend']=downtrend
df=df.fillna(0)
df['break']=df['uptrend']+df['downtrend']
df.drop('uptrend',axis=1,inplace=True)
df.drop('downtrend',axis=1,inplace=True)
buy=df.loc[upindex].reset_index()
sell=df.loc[downindex].reset_index()
print df
print buy
print sell
ret=(buy-sell)['A']
print ret