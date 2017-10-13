# -*- coding: utf-8 -*-

from gmsdk.api import StrategyBase
import sys
from gmsdk.api import StrategyBase
import pandas as pd
import numpy as np
import MAtest as ma
import logging
import logging.config

import datetime


PositionEffect_Open = 1             ## 开仓
PositionEffect_Close = 2            ## 平仓
PositionEffect_CloseToday = 3       ## 平今仓
PositionEffect_CloseYesterday = 4   ## 平昨仓

OrderSide_Bid = 1  ## 多方向
OrderSide_Ask = 2  ## 空方向

#订单状态
OrderStatus_New = 1,                        #已报
OrderStatus_PartiallyFilled = 2,            #部成
OrderStatus_Filled = 3,                     #已成
OrderStatus_DoneForDay = 4,                 #
OrderStatus_Canceled = 5,                   #已撤
OrderStatus_PendingCancel = 6,              #待撤
OrderStatus_Stopped = 7,                    #停止
OrderStatus_Rejected = 8,                   #已拒绝
OrderStatus_Suspended = 9,                  #挂起
OrderStatus_PendingNew = 10,                #待报
OrderStatus_Calculated = 11,                #计算
OrderStatus_Expired = 12,                   #已过期
OrderStatus_AcceptedForBidding = 13,        #接受竞价
OrderStatus_PendingReplace = 14             #待修改
class ShunlongWin(StrategyBase):

    def __init__(self, *args, **kwargs):
        super(ShunlongWin, self).__init__(*args, **kwargs)

        self.dailyBar = pd.DataFrame( columns=['strdatetime', 'utcdatetime', 'open', 'high', 'low', 'close', 'position', 'volume'])  # 保存原始的1分钟Bar数据
        self.dailyBarMin = pd.DataFrame(columns=['strdatetime', 'utcdatetime', 'open', 'high', 'low', 'close', 'position','volume'])  # 保存多分钟合并的Bar数据，分钟数由K_min确定
        self.MA = pd.DataFrame(columns=['strdatetime', 'utcdatetime', 'close', 'MA'])
        self.MACD = pd.DataFrame(columns=['strdatetime', 'utcdatetime', 'close', 'MACD', 'DEA', 'HIST', 'sema', 'lema'])
        self.WMAweight=[0.005,0.010,0.014,0.019,0.024,0.029,0.033,0.038,0.043,0.048,0.052,0.057,0.062,0.067,0.071,0.076,0.081,0.086,0.090,0.095]

        self.trendList = []  # 用来保存每一次趋势判断的情况
        self.buyMarketList = []  # 用来保存每一次买趋势的内容，包序号，x轴位置，时间，最高价，最低价，现价，类型
        self.sellMarketList = []  # 保存每一次卖趋势的内容
        self.buyFlag = 0  # 买卖标识，-1为卖，1为买

        self.positionHold = self.get_positions()

        self.buyInfo = pd.DataFrame(columns=['index', 'xpos', 'time', 'type', 'result'])

        # self.K_min=3 #采用多少分钟的K线，默认为3分钟，在on_bar中会判断并进行合并
        self.K_min = self.config.getint('para', 'K_min') or 3

        self.noticeMail = self.config.get('para', 'noticeMail')
        self.tradeStartHour = self.config.getint('para', 'tradeStartHour')
        self.tradeStartMin = self.config.getint('para', 'tradeStartMin')
        self.tradeEndHour = self.config.getint('para', 'tradeEndHour')
        self.tradeEndMin = self.config.getint('para', 'tradeEndMin')

        self.backwardDay = self.config.getint('para', 'backwardDay')
        self.stopLossRatio = self.config.getfloat('para', 'stoplossratio')
        self.MA_N=self.config.getint('para','MA_N')

        self.K_minCounter = 0  # 用来计算当前是合并周期内的第几根K线，在onBar中做判断使用
        self.last_update_time = datetime.datetime.now()  # 保存上一次 bar更新的时间，用来帮助判断是否出现空帧

        self.exchange_id, self.sec_id, buf = self.subscribe_symbols.split('.', 2)
        # 准备好数据
        self.dataPrepare()

    def on_login(self):
        pass

    def on_backtest_finish(self, indicator):
        self.dailyBar.to_csv('backtestdailyBar.csv')
        self.dailyBarMin.to_csv('backtestdailyBarMin.csv')
        self.MA.to_csv('backtestMA.csv')
        self.MACD.to_csv('backtestMACD.csv')
        self.buyInfo.to_csv('backtestBuyinfo.csv')
        pass

    def on_bar(self, bar):
        #实时只能取1分钟的K线，所以要先将1分钟线合并成多分钟K线，具体多少分钟由参数K_min定义
        #每次on_bar调用，先用数据保存到dailyBar中，再判断是否达到多分钟合并时间，是则进行合并，并执行一系列操作
        timenow=datetime.datetime.fromtimestamp(bar.utc_time)

        #先保存bar数据
        self.update_dailyBar(bar)
        barMin=int(timenow.minute)
        if (barMin+1) % self.K_min==0 and self.K_minCounter>=self.K_min:
            self.update_dailyBarMin(bar)
            self.updateMA()
            self.updateMACD()
            self.trendJudge()#趋势判断，在趋势判断中会给出buyFlag
            if self.buyFlag==1 :                             #买
                self.buyJudge(bar)
                self.buyFlag=0
            elif self.buyFlag==-1:                          #卖
                self.sellJudge(bar)
                self.buyFlag=0

    #开始运行时，准备好数据，主要是把当天的数据加载到缓存中
    def dataPrepare(self):
        startTime = datetime.time(self.tradeEndHour, self.tradeStartMin, 0).strftime("%H:%M:%S")
        if self.mode==4:
            d, t = self.start_time.split(' ', 1)
            y, m, d = d.split('-', 2)
            d = datetime.date(int(y), int(m), int(d))
            startDate=(d-datetime.timedelta(days=self.backwardDay)).strftime("%Y-%m-%d")
            endTime=self.start_time
        else:
            startDate=(datetime.date.today()-datetime.timedelta(days=self.backwardDay)).strftime("%Y-%m-%d")
            endTime=datetime.date.today().strftime("%Y-%m-%d")+' '+startTime
        sT=startDate+' '+startTime
        bars = self.get_bars(self.exchange_id+'.'+self.sec_id, 60, sT, endTime)
        #这里数据只用来计算MA
        rownum=0
        for bar in bars:
            rownum = self.update_dailyBar(bar)
            if rownum % self.K_min == 0 and rownum >= self.K_min:
                self.update_dailyBarMin(bar)
        self.prepareMA()
        self.prepareMACD()

        krow = self.dailyBarMin.shape[0]
        lastclose = self.dailyBarMin.ix[krow - 1, 'close']
        lastMA = self.MA.ix[self.MA.shape[0] - 1, 'MA']
        if lastclose>lastMA:self.trendList.append(1)
        elif lastclose<lastMA:self.trendList.append(-1)
        else:self.trendList.append(0)

        #下面要再做实盘下当天数据的处理
        if self.mode==2:
            pass
        if rownum>0:
            self.last_update_time = datetime.datetime.fromtimestamp(self.dailyBar.ix[rownum-1,'utcdatetime'])

        print("------------------------data prepared-----------------------------")
        pass

    def closeAllPosition(self):
        '''
        每日收盘前，平掉所有持仓
        :return:
        '''
        pl=self.get_positions()
        for p in pl:
            if p.side ==1:self.close_long(self.exchange_id,self.sec_id,0,p.volume)
            else: self.close_short(self.exchange_id,self.sec_id,0,p.volume)

    #更新dailyBar
    def update_dailyBar(self,bar):
        rownum=self.dailyBar.shape[0]
        self.dailyBar.loc[rownum] =[bar.strtime,bar.utc_time, bar.open, bar.high, bar.low, bar.close, bar.position,bar.volume]
        self.K_minCounter+=1
        return rownum+1

    #更新dailyBarMin
    def update_dailyBarMin(self,bar):
        '''
        K线合并后，取第一根K线的时间作为合并后的K线时间
        :param bar:
        :return:
        '''
        rownum=self.dailyBar.shape[0]
        if rownum <self.K_min:return
        self.dailyBarMin.loc[self.dailyBarMin.shape[0]] = \
            [self.dailyBar.ix[rownum - self.K_min]['strdatetime'],
             self.dailyBar.ix[rownum - self.K_min]['utcdatetime'],
             self.dailyBar.ix[rownum - self.K_min]['open'],  # 取合并周期内第一条K线的开盘
             max(self.dailyBar.iloc[rownum - self.K_min:rownum]['high']),  # 合并周期内最高价
             min(self.dailyBar.iloc[rownum - self.K_min:rownum]['low']),  # 合并周期内的最低价
             bar.close,  # 最后一条K线的收盘价
             bar.position, # 最后一条K线的仓位值
             sum(self.dailyBar.iloc[rownum -self.K_min:rownum]['volume'])] #v1.2版本加入成交量数据
        self.K_minCounter=0
        return True


    def trendJudge(self):
        '''
        趋势判断：
            如果上一周期收盘价在MA20下面，本周期收盘价在MA20上面，即为买点，开多
            如果上一周期收盘价在MA20上面，本周期收盘价在MA20下面，即为卖点，开空
        :param bar:
        :return:
        '''
        krow=self.dailyBarMin.shape[0]
        lastclose=self.dailyBarMin.ix[krow-1,'close']
        lastMA=self.MA.ix[self.MA.shape[0]-1,'MA']

        if lastclose>lastMA:trend=1
        elif lastclose<lastMA:trend=-1
        else:trend=self.trendList[-1]

        if trend==1 and self.trendList[-1]==-1:
            self.buyFlag=-1
        elif trend==-1 and self.trendList[-1]==1:
            self.buyFlag=1
        else:self.buyFlag=0
        self.trendList.append(trend)

        if self.buyFlag!=0:
            # 有行情时，保存行情信息
            row=self.dailyBarMin.shape[0]
            bar = self.dailyBarMin.iloc[row - 2]
            marketInfo = {'time': bar['strdatetime'],
                          'lastMA':lastMA,
                          'lastClose':lastclose,
                          'K':self.dailyBarMin.iloc[-1],
                          'type': self.buyFlag,
                          'result': 'init'
                          }
            if self.buyFlag==1:
                self.buyMarketList.append(marketInfo)
            elif self.buyFlag==-1:
                self.sellMarketList.append(marketInfo)

    def buyJudge(self,bar):
        '''
        :param bar:
        :return:
        '''
        # 1.1版本，平仓无交易区间限制，开仓才有交易区间限制
        # 上涨趋势中，判断是否持有空仓，有的话平掉空仓
        if self.positionHold:
            for p in self.positionHold:
                if p.side==OrderSide_Ask:
                    self.close_short(self.exchange_id,self.sec_id,0,p.volume)

        macdrow=self.MACD.shape[0]
        if self.MACD.ix[macdrow-1,'MACD']>self.MACD.ix[macdrow-1,'DEA']:
            self.open_long(self.exchange_id, self.sec_id, 0, 1)
            self.buyMarketList[-1]['result'] = 'buy success'
            print 'buy success'
            self.positionHold = self.get_positions()



    def sellJudge(self,bar):
        if self.positionHold:
            for p in self.positionHold:
                if p.side==OrderSide_Bid:
                    self.close_long(self.exchange_id,self.sec_id,0,p.volume)

        macdrow=self.MACD.shape[0]
        if self.MACD.ix[macdrow-1,'MACD']<self.MACD.ix[macdrow-1,'DEA']:
            self.open_short(self.exchange_id, self.sec_id, 0, 1)
            self.sellMarketList[-1]['result'] = 'sell success'
            print 'sell success'
            self.positionHold = self.get_positions()

    def prepareMA(self):
        '''
        self.MA = pd.DataFrame(columns=['strdatetime', 'utcdatetime', 'close', 'MD'])
        def calMA(data, N=5):
        :return:
        '''
        self.MA['strdatetime'] = self.dailyBarMin['strdatetime']
        self.MA['utcdatetime'] = self.dailyBarMin['utcdatetime']
        self.MA['close'] = self.dailyBarMin['close']
        self.MA['MA'] = ma.calMA(self.MA['close'],self.MA_N)
        #self.MA['MA']=ma.calWMA(self.MA['close'],self.WMAweight,self.MA_N)

    def prepareMACD(self):
        '''
        在dataPrepare准备完后，一次计算已有数据的MACD，保存到self.MACD中
        self.MACD=pd.DataFrame(columns=['strdatetime','utcdatetime','close','MACD','DEA','HIST','sema','lema'])
        :return:
        '''
        self.MACD['strdatetime']=self.dailyBarMin['strdatetime']
        self.MACD['utcdatetime']=self.dailyBarMin['utcdatetime']
        self.MACD['close']=self.dailyBarMin['close']
        self.MACD['MACD'],self.MACD['DEA'],self.MACD['HIST'],self.MACD['sema'],self.MACD['lema']\
            =ma.calMACD(self.MACD['close'])
        pass



    def updateMA(self):
        '''
        根据dailyBarMin最后一行的数据，计算出新的MA，并更新到MA表中
        def calNewMA(data,N=5):
        :return:
        '''
        brow=self.dailyBarMin.shape[0]
        mrow=self.MA.shape[0]
        laststrdatetime=self.dailyBarMin.ix[brow-1,'strdatetime']
        lastutcdatetime = self.dailyBarMin.ix[brow - 1, 'utcdatetime']
        lastClose=self.dailyBarMin.ix[brow-1,'close']
        lastma=ma.calNewMA(self.dailyBarMin['close'],self.MA_N)
        #lastma=ma.calNewWMA(self.dailyBarMin['close'],self.WMAweight,self.MA_N)
        self.MA.loc[mrow] = [laststrdatetime,lastutcdatetime, lastClose, lastma]
        pass

    def updateMACD(self):
        '''
        根据dailyBarMin最后一行的数据，计算出新的MACD，并更新到MACD表中
        :return:
        '''
        brow=self.dailyBarMin.shape[0]
        mrow=self.MACD.shape[0]
        laststrdatetime=self.dailyBarMin.ix[brow-1,'strdatetime']
        lastutcdatetime = self.dailyBarMin.ix[brow - 1, 'utcdatetime']
        lastClose=self.dailyBarMin.ix[brow-1,'close']
        lastdea=self.MACD.ix[mrow-1,'DEA']
        lastsema=self.MACD.ix[mrow-1,'sema']
        lastlema=self.MACD.ix[mrow-1,'lema']
        macd,dea,hist,sema,lema=ma.calNewMACD(lastClose,lastdea,lastsema,lastlema)
        self.MACD.loc[mrow] = [laststrdatetime,lastutcdatetime, lastClose, macd, dea, hist, sema,lema]
        pass

if __name__ == '__main__':
    ini_file = sys.argv[1] if len(sys.argv) > 1 else 'meanWin.ini'
    logging.config.fileConfig(ini_file)
    myStrategy = ShunlongWin(config_file=ini_file)
    ret = myStrategy.run()
    print('exit code: ', ret)