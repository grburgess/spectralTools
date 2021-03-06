#import pyfits as pf
import astropy.io.fits as pf
from numpy import mean, dtype, float64, array, concatenate, asarray
from copy import deepcopy
import gc
from spectralTools.models import modelLookup

def f5(seq, idfun=None):  
    # order preserving 
    if idfun is None: 
        def idfun(x): return x 
    seen = {} 
    result = [] 
    for item in seq: 
        marker = idfun(item) 
        # in old Python versions: 
        # if seen.has_key(marker) 
        # but in new ones: 
        if marker in seen: continue 
        seen[marker] = 1 
        result.append(item) 
    return result


keV2erg =1.60217646e-9

class scatReader:
    '''
    SCATReadrer reads in a filename of an scat file made by RMFIT
    and turns it into a python object. It stores the covariance matrix,
    fit params, fluxes from RMFIT, and time bins for EACH model.

    It can read single fits or batch fits.
    
    It interfaces with other progams for plotting and flux calculation

    The add operator is overloaded so that two SCATReaders can be added.
    At the moment the temporal ordering is based on you adding the files
    in the proper order
    

    '''
    def __init__(self, fileName, silent=True):
        

        self.effArea = True
        if fileName == "summed":
            return
        
        self.modelNames = []
        self.models = []


        self.silent=silent

        self.scat  = pf.open(fileName,memmap=False) #The false statement means the whole file is loaded in
        if not self.silent:
            print "Opening SCAT file: "+fileName

        self.tBins  = self.scat[2].data['TIMEBIN']
        self.meanTbins = array(map(mean,self.tBins))
        #self.met=

        self.phtFlux = self.scat[2].data['PHTFLUX']
        self.phtFluence = self.scat[2].data['PHTFLNC']
        self.eneFlux = self.scat[2].data['NRGFLUX']
        self.eneFluence = self.scat[2].data['NRGFLNC']
        self.covars = self.scat[2].data['COVARMAT']
        
        self.dof = array(map(float,(self.scat[2].data['CHSQDOF'])))
        self.cstat = self.scat[2].data['REDCHSQ'][:,1]*self.dof
        

        # I may take this out at some point
        self.batchFit = False
        self.ExtractModels()
        self.FormatCovarMat()
        if not self.silent:
            print "Closing SCAT file\n"
        self.scat.close()
        del self.scat
        gc.collect()



    def __add__(self,other):

        

        if other.modelNames != self.modelNames:
            print "modelNames do not match"
            return
          
        new = scatReader('summed')
        new.modelNames = self.modelNames
        new.numParams = self.numParams
        new.paramNames = self.paramNames

        new.tBins = array(concatenate((self.tBins,other.tBins)))
        new.meanTbins=array(map(mean,new.tBins))
        
        new.phtFlux = concatenate((self.phtFlux,other.phtFlux))

        new.phtFluence = concatenate((self.phtFluence,other.phtFluence))

        new.covars = concatenate((self.covars,other.covars))
        new.dof = concatenate((self.dof,other.dof))
        new.cstat = concatenate((self.cstat,other.cstat))




        tmp1 = []

    
        dicString = ['values','-','+']

        
        for x in self.modelNames:
            
            
            errorsplus = concatenate((self.models[x]['+'], other.models[x]['+']  ))
            errorsminus = concatenate((self.models[x]['-'], other.models[x]['-']  ))
            values = concatenate((self.models[x]['values'], other.models[x]['values'] ) )



            tmp = dict(zip(dicString,[values,errorsminus,errorsplus]))
            
            tmp1.append(tmp)


        new.models = dict(zip(self.modelNames,tmp1))

            
              

        return new 



    def GetParamArray(self, model,param):
        '''
        Returns a paramerter array for that model. This is NOT a
        structured list. The params are the first column and the 
        errors are the last two columns.

        '''
        paramArr = deepcopy(self.models[model]['values'][param])
        paramErrplus = deepcopy(self.models[model]['+'][param])
        paramErrminus = deepcopy(self.models[model]['-'][param])
        tmp = asarray([paramArr,paramErrminus,paramErrplus]).transpose()[0]
        #tmp.dtype = dtype([(float,'value'),(float,'error')])
        return tmp
        



    def __repr__(self):

        info = "SCAT Models:\n"
        for x in self.modelNames:
            info = info+x+"\n"
        info = info+"\n\n"

        info = info+"Time Bins:\n"
        for x in self.tBins:
            info = info + str(x[0])+' : '+str(x[1])+'\n'

        info = info+"\n\n"

        




        return info


    def ExtractModels(self):


        header = self.scat[2].header.cards
        
        # Sort out the models in the scat file
        tmp = filter (lambda x: type(x.value)==str ,header)
        
        tmp1 = filter (lambda x:'FIT' not in x.value and  'PARAM' in  x.value ,tmp)
        self.numParams =  len(tmp1)
        
        tmp2 = map(lambda x: x.comment.split(':')[0].strip(), tmp1)
       
        # Find the unique entries in the list 
        self.modelNames = f5(tmp2)
        
        del tmp
        del tmp1
        del tmp2
        
        if 'Eff. Area Corr.' in self.modelNames:
            if not self.silent:
                print "Awww snap. There's an effective area correction in here. "
                print "It will be removed and the covariance matrix altered"
            self.effArea = True
            self.modelNames.remove('Eff. Area Corr.')

        # Now extract the parameters from the models

        self.paramNames  =  map(lambda x: map(lambda y: y.comment.split(':')[1].strip() ,filter(lambda z: x in z.comment, header) ), self.modelNames)
       
        if self.effArea:
            np = 0
            for x in self.paramNames:
                np+=len(x)

            self.numEffCor = (self.numParams - np)*-1
            self.numParams = np
        
        tmpParam =  map( lambda x: map(lambda y: y.value ,filter(lambda z: x in z.comment  ,header) ), self.modelNames)
        tmp =  map( lambda x: array( map(lambda y: self.scat[2].data[y].tolist() ,x)).transpose().tolist()  , tmpParam)
        tmp = map( lambda x: map(array,x) ,tmp)
        tmp2 =  map ( lambda x:   map(lambda y:  (y, float64)    ,x)  , self.paramNames)
        #tmp3 = map ( lambda x:   map(lambda y:  ([y,y], (float64, flo))    ,x)  , self.paramNames)
        #Assign dtypes to the params
   
        
        

        for x,y in zip(tmp,tmp2):
            for z in x:
                #print y
                z.dtype = dtype(y)
                
                #z.dtype = dtype(y)

        dicString = ['values','-','+']
        if len(tmp[0]) != len(dicString):
            if not self.silent:
                print "The error column is missing"
                print "Duplicating 1-sided errors from batch fit!"
            self.batchFit = True
            for t in tmp:
                t.append(t[1])
            
        
        tmp = map(lambda x: dict(zip(dicString,x))   ,tmp)

        self.models = dict(zip(self.modelNames,tmp))

        self.numModels = len(self.modelNames)

        del tmp
        del tmp2

  
    def FormatCovarMat(self):


        length = self.numParams
        
        covars = []
        
        for x in self.covars:
            
            covar = []
            
 
            for i in range(length):
                

                tmp = []

                for j in range(length):
                   

                    #tmp.append(x[i*length+j])
                    tmp.append(x[i][j])

                covar.append(tmp)
                    
            covars.append(array(covar))
        #if self.effArea and not self.batchFit:
        #    print "Correcting COVAR matrix"
        #    print self.numEffCor
            
        #    for i in range(len(covars)):
        #        print "test"
                #covars[i] = covars[i][:self.numEffCor,:self.numEffCor]
                #self.numParams = self.numParams - self.numEffCor
        self.covars=covars





    def _TimeIndex(self,t):

        indx = self.meanTbins.searchsorted(t)
        test=[abs(self.meanTbins[indx]-t),abs(self.meanTbins[indx-1]-t)]


        val2 = min(test)



        indx = indx-test.index(val2)
        return indx



    def _CalcModel(self,energy,params,modelName="Band's GRB, Epeak"):
        '''
        Returns the photon flux of the model at a given energy

        '''

        model = modelLookup[modelName]

        return model(energy,*params)

    
           
    def SpecificEnergyFlux(self,time, energy,modelName="Band's GRB, Epeak"):



        tIndx = self._TimeIndex(time)


        params = self.models[modelName]['values'][tIndx][0]

        
        
        phtFlux = self._CalcModel(energy,params,modelName)

        return energy*phtFlux*keV2erg
        




        

    


    
        
        
        

        

            

        
