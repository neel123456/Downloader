### Import Libraries ###
import requests
import urllib.request as ur
import sys,os,threading,time
from bs4 import BeautifulSoup as bs
### Import Files ###
import utils

class downloadUrl(object):
    def __init__(self,url,title=None):
        self.url=url
        self.byteAllow=True
        self.headers=None
        self.frags=64
        self.title=utils.removeSlash(title)
        self.length=None
        self.done=False
        self.percent=None
        self.fraglist=None
        self.fragsize=[-1 for i in range(self.frags)]
        self.donesize=[0 for i in range(self.frags)]
        self.skipmerge=False
        self.running=True
        self.chunk=1*1024
        self.wait=5
        self.tries=3
        if not self.title:
            self.title=url.split('/')[-1]
            if '?' in self.title:
                self.title = self.title.split('?')[0]
            print("title set to "+self.title)
        
    def __str__(self):
        return str("url: "+self.url)

    def sendHead(self):
        print("sending Head request")
        response=requests.head(self.url)
        if response.status_code==200 and 'Content-Length' in response.headers:
            print("OK 200")
            self.headers=response.headers
            self.length=int(self.headers['Content-Length'])
            print("length: "+str(self.length) + " " + str(self.length / 1024 / 1024) + "MB")
            assert self.length>0,"Something went wrong"

##            if self.headers['Accept-Ranges']=='bytes':
##                self.byteAllow=True
##            else:
##                self.byteAllow=False
        elif response.status_code>300 and response.status_code<309:
            print(str(response.status_code)+" "+response.reason)
            print("following redirection")
            self.url=response.headers['Location']
            self.sendHead()
        else:
            print(str(response.status_code)+"received"+response.reason)
            self.byteAllow=False
            self.headers=response.headers
            self.length=False
            
    def downloadOld(self):
        chunk=16*1024    
        ###  Prepare request
        sendheaders={'User-Agent':'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_9_3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/35.0.1916.47 Safari/537.36'}
        reqst=ur.Request(self.url,headers=sendheaders)
        data=ur.urlopen(reqst)
        fp=open(self.title,"wb")
        percentThread=threading.Thread(target=utils.checkSize,args=(self.title,self.length))
        percentThread.start()
        while True:
            cnk=data.read(chunk)
            if not cnk: 
                break
            fp.write(cnk)
        fp.close()
        self.done=True
        percentThread.join()
        print()
        print("done!")

    def downloadFrag(self,start,end,num,try_no):
        oldstart=start
        fname="." + self.title + ".frag" + str(num)
        self.fragsize[num]=end-start+1
        while True:
            start = oldstart
            if os.access(fname,os.F_OK):
                start+=os.stat(fname).st_size
                self.donesize[num]=os.stat(fname).st_size
                assert start-1<=end,"Cannot resume! start=%d end=%d num=%d" %(start,end,num)
                if start==end+1:
                    return;
            print("starting download for %d frag " % num,end='\r')
            sendheaders={'Range':'bytes=%d-%d'%(start,end),'User-Agent':'Mozilla/5.0 \
    (Macintosh; Intel Mac OS X 10_9_3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/35.0.1916.47 Safari/537.36'}
            connection=ur.Request(self.url,None,sendheaders)
            try:
                down=ur.urlopen(connection,timeout=20)
                if down.status != 206:
                    print("Server Does not support partial content", end = "\r")
                    self.skipmerge=True;
                    return;
            except:
                if try_no > 0:
                    self.downloadFrag(oldstart, end, num, try_no - 1)
                    return;
                else:
                    self.skipmerge=True;
                    print("Error occured frag=%d"%num)
                    return -1;
            fp=open(fname,"ab")
            writer=threading.Thread(target=self.writeChunks,args=(fp,down,num))
            writer.start()
            count=0
            while True:
                downloaded=self.donesize[num]
                if writer.is_alive():
                    time.sleep(1)
                    count+=1                ## wait for something to change
                    if count%self.wait==0 and self.donesize[num]==downloaded:
                        fp.close()     
                        break
                else:
                    return
        
    def writeChunks(self,f,connection,num):
        try:
            while(True):
                cnk=connection.read(self.chunk)
                if not cnk:
                    break
                f.write(cnk)
                self.donesize[num]+=len(cnk)
        except:
            return -1;  
        

    def setconstantfrags(self,kbs):
        if self.length==None:
            self.sendHead()
        self.fraglist=[]
        size=1024*kbs
        first=0
        last=size-1
        cnt=0
        while first<=self.length-1:
            if last>self.length-1:
                last=self.length-1
            self.fraglist.append((first,last))
            first=last+1
            last=first+size-1
            cnt+=1
        self.frags=cnt
        self.fragsize=[-1 for i in range(self.frags)]
        self.donesize=[0 for i in range(self.frags)]
        print(self.frags)

    def setFrags(self, frags = 32):
        if self.length/(1024*1024.0) < 32:
            self.setconstantfrags(256)
        elif self.length/(1024*1024.0) < 1024:
            self.setconstantfrags(256)
        else:
            self.setconstantfrags(10*1024)
            
    def bbdownload(self,frags=96):
        if self.length==False or self.byteAllow==False:
            print("Can not download by fragments.")
            print("Falling back to old download style.")
            self.downloadOld()
            return;
        else:
            self.sendHead()
            if os.access(self.title,os.F_OK) and os.stat(self.title).st_size==self.length:
                print("looks like file is downloaded already")
                return;
            print("downloading "+'%.2f'%(self.length/(1024*1024.0))+" MB");
            
            self.setFrags();
            self.wait=3
            threadlist=[]
            nextFrag=0
            progress=threading.Thread(target=self.generateProgressBar)
            threadlist.append(progress)
            progress.start()
            while True:                             ## Change here...Bug: active count may be more than actual, The orphened connections.. 
                if threading.active_count()<1+frags:
                    t=threading.Thread(target=self.downloadFrag,kwargs={'start':self.fraglist[nextFrag][0],\
                                                                        'end':self.fraglist[nextFrag][1],\
                                                                        'num':nextFrag,\
                                                                        'try_no':self.tries})
                    t.start()
                    threadlist.append(t)
                    nextFrag+=1
                    time.sleep(0.001)               ## Server should not feel that she's under attack..
                    if nextFrag==self.frags:
                        break
            for i in threadlist:
                i.join()
            self.done = True;
            print("done downloading")
            if self.skipmerge:
                print("Can't merge...still have to download the DEAD")
                self.running=False
                return;
            print("Starting to merge %d files"%(self.frags))
            self.running=False
            utils.catAll(self.title,self.frags)
            print()

    def generateProgressBar(self):
        sleepTime=0.2         ### in seconds(Using variable to manage speeds ###
        prevDoneSize=0
        while True:
            if not self.running:
                break;
            curDoneSize=sum(self.donesize)
            utils.printProgressBar(curDoneSize*100.0/self.length,speed=(curDoneSize-prevDoneSize)/sleepTime/1024)
            if self.donesize==self.fragsize:
                break
            time.sleep(sleepTime)
            prevDoneSize=curDoneSize
